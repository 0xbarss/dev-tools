"""`devtools grep` — fast project-aware search (spec §6).

Note: unlike most other commands, the spec's examples never pass a project
positional for `grep` — project resolution goes through the global
--project flag / default-project resolution only.
"""

from __future__ import annotations

from typing import List, Optional

import typer

from devtools.commands._shared import build_ignore_rules, resolve_project
from devtools.core.fzf_integration import NOT_INSTALLED_HINT, run_fzf
from devtools.core.grep_engine import grep as grep_engine
from devtools.core.output import render_table

app = typer.Typer()


@app.command()
def grep(
    ctx: typer.Context,
    query: str = typer.Argument(..., help="Text or pattern to search for."),
    regex: bool = typer.Option(False, "--regex/--no-regex", help="Treat query as a regex pattern (default: literal string)."),
    lang: List[str] = typer.Option([], "--lang", help="Restrict to these languages (repeatable)."),
    context: int = typer.Option(0, "--context", help="Lines of context to show around each match."),
    case_sensitive: bool = typer.Option(True, "--case-sensitive/--ignore-case", help="Case-sensitive matching (default: on)."),
    fzf: bool = typer.Option(False, "--fzf", help="Pick matches interactively via fzf (falls back to normal output if fzf isn't installed)."),
) -> None:
    """Search the resolved project for `query`."""
    state = ctx.obj
    proj = resolve_project(ctx)
    rules = build_ignore_rules(ctx, proj)

    matches = grep_engine(
        proj.resolved_path,
        rules,
        query,
        regex=regex,
        languages=list(lang) or None,
        context=context,
        case_sensitive=case_sensitive,
    )

    if state.output.is_json:
        state.output.emit_json(
            [
                {
                    "path": m.rel_path,
                    "line": m.line_number,
                    "text": m.line,
                    "context_before": m.context_before,
                    "context_after": m.context_after,
                }
                for m in matches
            ]
        )
        return

    if not matches:
        state.output.print(f"No matches for {query!r} in '{proj.name}'.")
        return

    if fzf:
        candidates = [f"{m.rel_path}:{m.line_number}: {m.line.strip()[:200]}" for m in matches]
        selected = run_fzf(candidates, prompt=f"{query} > ")
        if selected is None:
            state.output.print(f"[dim]{NOT_INSTALLED_HINT}[/dim]" if not candidates else "[dim]No selection made.[/dim]")
        else:
            selected_set = set(selected)
            matches = [m for m, c in zip(matches, candidates) if c in selected_set]
            if not matches:
                return

    if context:
        for m in matches:
            state.output.print(f"[bold cyan]{m.rel_path}:{m.line_number}[/bold cyan]")
            for line in m.context_before:
                state.output.print(f"  {line}")
            state.output.print(f"[bold]> {m.line}[/bold]")
            for line in m.context_after:
                state.output.print(f"  {line}")
            state.output.print("")
    else:
        rows = [[m.rel_path, m.line_number, m.line.strip()[:120]] for m in matches]
        render_table(state.output, f"Matches for {query!r}", ["path", "line", "text"], rows, json_key="matches")
