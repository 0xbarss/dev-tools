"""`devtools context` — a lighter, task-scoped sibling of `bundle` (spec §6).

Combines grep-style relevance search with collect-style formatting, designed
to be piped straight into another LLM call (spec §9, AI-Assisted Workflows).
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import typer

from devtools.commands._shared import build_ignore_rules, resolve_project
from devtools.core.collector import collect_files, render_markdown
from devtools.core.export_engine import cache_output
from devtools.core.search_engine import search

app = typer.Typer()


@app.command()
def context(
    ctx: typer.Context,
    project: Optional[str] = typer.Argument(None, help="Project to build context for."),
    question: Optional[str] = typer.Argument(None, help="Natural-language question, e.g. 'how does auth work'."),
    files: List[str] = typer.Option([], "--files", help="Explicit glob(s) of files to include instead of searching (repeatable)."),
    symbol: Optional[str] = typer.Option(None, "--symbol", help="Also search for this specific symbol name."),
    top: int = typer.Option(8, "--top", help="Max number of files to include when using relevance search."),
    stdout: bool = typer.Option(True, "--stdout/--no-stdout", help="Print to stdout (default) instead of writing a file."),
) -> None:
    """Build a minimal, task-scoped context payload for a specific question."""
    state = ctx.obj
    proj = resolve_project(ctx, project)
    root = proj.resolved_path
    rules = build_ignore_rules(ctx, proj)

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

    result = collect_files(root, rules, only_paths=selected_paths)
    title = f"{proj.name} context: {question or symbol or ', '.join(files)}"

    if state.output.is_json:
        from devtools.core.collector import render_json

        payload = render_json(result)
        state.output.emit_json(payload)
        cache_output("context", proj.name, payload)
        return

    content = render_markdown(result, proj.name, title=title)
    if stdout:
        print(content)
    else:
        out_path = Path.cwd() / f"{proj.name}_context.md"
        out_path.write_text(content, encoding="utf-8")
        state.output.print(f"[green]Wrote {out_path}[/green]")

    state.output.print(f"{len(result.files)} files, ~{result.total_tokens} tokens", )
    cache_output("context", proj.name, {"files": [f.rel_path for f in result.files], "tokens": result.total_tokens})