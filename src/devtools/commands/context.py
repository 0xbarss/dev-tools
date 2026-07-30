"""`devtools context` — a lighter, task-scoped sibling of `bundle` (spec §6).

Combines grep-style relevance search with collect-style formatting, designed
to be piped straight into another LLM call (spec §9, AI-Assisted Workflows).

`--compress` (backlog #30, "context compression") is the map-reduce sibling
of `--max-tokens`'s existing hard truncation: instead of silently dropping
files that don't fit the budget, it AI-summarizes them (via
`summarize_engine.map_reduce_summarize`, shared with `devtools summarize
--repo`) and appends that as a compact appendix, so nothing is lost outright.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import typer

from devtools.commands._shared import build_ignore_rules, fail, resolve_project
from devtools.core.collector import collect_files, render_markdown
from devtools.core.exit_codes import GENERAL_ERROR
from devtools.core.export_engine import cache_output
from devtools.core.llm_client import LLMClientError, get_client
from devtools.core.search_engine import search
from devtools.core.summarize_engine import map_reduce_summarize

app = typer.Typer()


@app.command()
def context(
    ctx: typer.Context,
    project: Optional[str] = typer.Argument(None, help="Project to build context for."),
    question: Optional[str] = typer.Argument(None, help="Natural-language question, e.g. 'how does auth work'."),
    files: List[str] = typer.Option([], "--files", help="Explicit glob(s) of files to include instead of searching (repeatable)."),
    symbol: Optional[str] = typer.Option(None, "--symbol", help="Also search for this specific symbol name."),
    top: int = typer.Option(8, "--top", help="Max number of files to include when using relevance search."),
    max_tokens: Optional[int] = typer.Option(None, "--max-tokens", help="Token budget for included files; overflow is dropped unless --compress is set."),
    compress: bool = typer.Option(False, "--compress", help="Instead of dropping files past --max-tokens, AI-summarize them into a compact appendix (backlog #30)."),
    stdout: bool = typer.Option(True, "--stdout/--no-stdout", help="Print to stdout (default) instead of writing a file."),
) -> None:
    """Build a minimal, task-scoped context payload for a specific question."""
    state = ctx.obj
    proj = resolve_project(ctx, project)
    root = proj.resolved_path
    rules = build_ignore_rules(ctx, proj)

    if compress and max_tokens is None:
        fail(ctx, GENERAL_ERROR, "--compress requires --max-tokens (nothing to compress without a budget).")
        return

    if files:
        selected_paths = [p for pattern in files for p in root.glob(pattern) if p.is_file()]
    else:
        query = symbol or question or ""
        if not query:
            state.output.error("Provide a question, --symbol, or --files to scope the context.")
            raise typer.Exit(code=2)
        hits = search(root, rules, query)
        if symbol and question:
            hits_by_symbol = {h.rel_path: h for h in search(root, rules, symbol)}
            for h in hits:
                if h.rel_path in hits_by_symbol:
                    h.score += hits_by_symbol[h.rel_path].score
            hits.sort(key=lambda h: h.score, reverse=True)
        selected_paths = [root / h.rel_path for h in hits[:top]]

    result = collect_files(root, rules, only_paths=selected_paths, max_tokens=max_tokens)
    title = f"{proj.name} context: {question or symbol or ', '.join(files)}"

    compressed_appendix: str | None = None
    if compress and result.truncated:
        included = {f.rel_path for f in result.files}
        excluded = {p for p in result.skipped_binary} | {p for p in result.skipped_too_large}
        overflow_paths = [p for p in selected_paths if _rel(p, root) not in included and _rel(p, root) not in excluded]
        if overflow_paths:
            try:
                client = get_client(state.settings)
                overflow_result = collect_files(root, rules, only_paths=overflow_paths)
                _summaries, compressed_appendix = map_reduce_summarize(overflow_result.files, client)
            except LLMClientError as exc:
                state.output.warn(f"--compress requested but AI summarization failed ({exc}); overflow files were dropped instead.")

    if state.output.is_json:
        from devtools.core.collector import render_json

        payload = render_json(result)
        if compressed_appendix is not None:
            payload["compressed_appendix"] = compressed_appendix
        state.output.emit_json(payload)
        cache_output("context", proj.name, payload)
        return

    content = render_markdown(result, proj.name, title=title)
    if compressed_appendix is not None:
        content += "\n## Compressed context (AI-summarized overflow)\n\n" + compressed_appendix + "\n"
    if stdout:
        print(content)
    else:
        out_path = Path.cwd() / f"{proj.name}_context.md"
        out_path.write_text(content, encoding="utf-8")
        state.output.print(f"[green]Wrote {out_path}[/green]")

    state.output.print(f"{len(result.files)} files, ~{result.total_tokens} tokens", )
    cache_output("context", proj.name, {"files": [f.rel_path for f in result.files], "tokens": result.total_tokens})


def _rel(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)
