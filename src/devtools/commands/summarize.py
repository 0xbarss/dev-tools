"""`devtools summarize` — AI architecture overview (proposal §4, backlog #22)."""

from __future__ import annotations

from typing import List, Optional

import typer

from devtools.commands._shared import build_ignore_rules, fail, resolve_project
from devtools.core.exit_codes import GENERAL_ERROR
from devtools.core.export_engine import cache_output
from devtools.core.llm_client import LLMClientError, get_client
from devtools.core.summarize_engine import render_markdown, summarize_repo

app = typer.Typer()


@app.command()
def summarize(
    ctx: typer.Context,
    project: Optional[str] = typer.Argument(None, help="Project to summarize."),
    repo: bool = typer.Option(True, "--repo/--no-repo", help="Summarize the whole repository (currently the only mode)."),
    lang: List[str] = typer.Option([], "--lang", help="Limit to specific language(s) (repeatable)."),
    chunk_size: int = typer.Option(12_000, "--chunk-size", help="Approx. tokens per map-reduce chunk."),
) -> None:
    """Draft an ARCHITECTURE.md-style overview via a map-reduce pass over
    the repo: each chunk is summarized, then synthesized into one overview."""
    state = ctx.obj
    proj = resolve_project(ctx, project)
    rules = build_ignore_rules(ctx, proj)

    if not repo:
        fail(ctx, GENERAL_ERROR, "`summarize` currently only supports --repo (whole-repository) mode.")
        return

    try:
        client = get_client(state.settings)
        report = summarize_repo(proj.resolved_path, rules, client, languages=lang or None, chunk_size=chunk_size)
    except LLMClientError as exc:
        fail(ctx, GENERAL_ERROR, str(exc))
        return

    if state.output.is_json:
        payload = {"file_count": report.file_count, "chunk_count": report.chunk_count, "overview": report.overview}
        state.output.emit_json(payload)
        cache_output("summarize", proj.name, payload)
        return

    content = render_markdown(report, proj.name)
    print(content)
    cache_output("summarize", proj.name, {"file_count": report.file_count, "chunk_count": report.chunk_count})
