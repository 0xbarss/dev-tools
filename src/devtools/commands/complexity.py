"""`devtools complexity` — per-function cyclomatic complexity (proposal
#14). Stays thin per the existing `commands/` convention; all real logic
lives in `core/complexity_engine.py`."""

from __future__ import annotations

from typing import Optional

import typer

from devtools.commands._shared import build_ignore_rules, resolve_project
from devtools.core.complexity_engine import compute_complexity
from devtools.core.exit_codes import CHECK_FAILED
from devtools.core.export_engine import cache_output
from devtools.core.output import render_table

app = typer.Typer()


@app.command()
def complexity(
    ctx: typer.Context,
    project: Optional[str] = typer.Argument(None, help="Project to analyze."),
    top: int = typer.Option(20, "--top", help="How many highest-complexity functions to show."),
    threshold: int = typer.Option(10, "--threshold", help="Flag functions at or above this complexity."),
    ci: bool = typer.Option(False, "--ci", help="Exit 5 if any function is at or above --threshold."),
) -> None:
    """Report per-function cyclomatic complexity (Python only today),
    ranked highest-first — feeds the future `health`/`hotspots` commands."""
    state = ctx.obj
    proj = resolve_project(ctx, project)
    rules = build_ignore_rules(ctx, proj)

    files = compute_complexity(proj.resolved_path, rules)

    rows = [
        (f.rel_path, fn.qualname, fn.lineno, fn.complexity)
        for f in files
        for fn in f.functions
    ]
    rows.sort(key=lambda r: r[3], reverse=True)
    flagged = [r for r in rows if r[3] >= threshold]
    top_rows = rows[:top]

    if state.output.is_json:
        payload = {
            "functions": [{"file": r[0], "function": r[1], "line": r[2], "complexity": r[3]} for r in rows],
            "flagged": [{"file": r[0], "function": r[1], "line": r[2], "complexity": r[3]} for r in flagged],
            "threshold": threshold,
        }
        state.output.emit_json(payload)
        cache_output("complexity", proj.name, payload)
    else:
        if not rows:
            state.output.print(f"[dim]No Python functions found to analyze in '{proj.name}'.[/dim]")
        else:
            render_table(
                state.output,
                f"{proj.name} — complexity (top {len(top_rows)})",
                ["file", "function", "line", "complexity"],
                [[r[0], r[1], r[2], r[3]] for r in top_rows],
            )
            if flagged:
                state.output.warn(f"{len(flagged)} function(s) at or above complexity threshold {threshold}.")
        cache_output(
            "complexity",
            proj.name,
            {"functions": [{"file": r[0], "function": r[1], "complexity": r[3]} for r in rows]},
        )

    if ci and flagged:
        state.exit_code = CHECK_FAILED
        raise typer.Exit(code=CHECK_FAILED)