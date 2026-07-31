"""`devtools ask` — retrieval-augmented Q&A over a project's persistent RAG
chunk index (proposal deep-dive #25, `devtools index build --rag`).

Distinct from `devtools context`/`devtools explain`, both of which re-scan
and re-rank the filesystem on every call: `ask` only ever reads from the
already-built, already-chunked, already-vectorized SQLite index, so repeat
questions against the same project are cheap and don't touch disk beyond
the index file itself. Build (or refresh) that index first with
`devtools index build --rag <project>`.
"""

from __future__ import annotations

from typing import Optional

import typer

from devtools.commands._shared import fail, resolve_project
from devtools.core.exit_codes import GENERAL_ERROR
from devtools.core.export_engine import cache_output
from devtools.core.llm_client import LLMClientError, get_client
from devtools.core.rag_index import RagAnswer
from devtools.core.rag_index import generate_answer
from devtools.core.rag_index import retrieve as retrieve_chunks

app = typer.Typer()


@app.command()
def ask(
    ctx: typer.Context,
    project: Optional[str] = typer.Argument(None, help="Project to ask about."),
    question: str = typer.Argument(..., help="Natural-language question, e.g. 'how does auth work'."),
    top: int = typer.Option(6, "--top", help="Number of chunks to retrieve from the RAG index."),
) -> None:
    """Answer a question using the project's persistent RAG chunk index.

    Requires the index to already exist -- run `devtools index build --rag`
    first (and re-run it after significant changes; `devtools index status
    --rag` reports whether it's stale)."""
    state = ctx.obj
    proj = resolve_project(ctx, project)

    # Check the (free, deterministic) index before requiring an AI provider
    # to be configured -- same ordering `search --semantic` uses when no
    # index has been built yet.
    chunks = retrieve_chunks(proj.name, question, top_k=top)
    if not chunks:
        state.output.print(
            "No RAG index found (or nothing matched) for this project. "
            "Run `devtools index build --rag <project>` first, then ask again."
        )
        return

    try:
        client = get_client(state.settings)
        answer_text = generate_answer(question, chunks, client)
    except LLMClientError as exc:
        fail(ctx, GENERAL_ERROR, str(exc))
        return

    result = RagAnswer(answer=answer_text, sources=chunks, used_index=True)

    if state.output.is_json:
        payload = {
            "question": question,
            "answer": result.answer,
            "sources": [
                {
                    "path": c.rel_path,
                    "start_line": c.start_line,
                    "end_line": c.end_line,
                    "score": c.score,
                }
                for c in result.sources
            ],
        }
        state.output.emit_json(payload)
        cache_output("ask", proj.name, payload)
        return

    state.output.print(result.answer)
    state.output.print("")
    state.output.print("[dim]Sources:[/dim]")
    for c in result.sources:
        state.output.print(f"[dim]  {c.rel_path}:{c.start_line}-{c.end_line} (score {c.score})[/dim]")
    cache_output("ask", proj.name, {"question": question, "sources": [c.rel_path for c in result.sources]})
