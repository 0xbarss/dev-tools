"""`devtools deadcode` — unused imports/functions/classes (proposal #11).
Stays thin per the existing `commands/` convention; all real logic lives in
`core/deadcode_engine.py`."""

from __future__ import annotations

from typing import Optional

import typer

from devtools.commands._shared import build_ignore_rules, resolve_project
from devtools.core.deadcode_engine import compute_deadcode
from devtools.core.exit_codes import CHECK_FAILED
from devtools.core.export_engine import cache_output
from devtools.core.output import render_table

app = typer.Typer()


@app.command()
def deadcode(
    ctx: typer.Context,
    project: Optional[str] = typer.Argument(None, help="Project to scan."),
    include_decorated: bool = typer.Option(
        False,
        "--include-decorated",
        help="Also flag decorated functions/classes (higher false-positive rate: routes, fixtures, CLI commands, etc.).",
    ),
    include_tests: bool = typer.Option(
        False, "--include-tests", help="Also flag test_* functions (usually invoked only by test discovery)."
    ),
    ci: bool = typer.Option(False, "--ci", help="Exit 5 if anything is found."),
) -> None:
    """Find unused imports and unused module-level functions/classes (Python only).

    Cross-file "unused" detection is a name-occurrence scan, not a real
    call graph, so treat findings as leads to check, not guaranteed dead
    code — dynamic dispatch, reflection, and framework-invoked callbacks
    can all still show up here as false positives.
    """
    state = ctx.obj
    proj = resolve_project(ctx, project)
    rules = build_ignore_rules(ctx, proj)

    report = compute_deadcode(
        proj.resolved_path, rules, include_decorated=include_decorated, include_tests=include_tests
    )

    if state.output.is_json:
        payload = {
            "unused_imports": [{"file": i.rel_path, "line": i.lineno, "name": i.name} for i in report.unused_imports],
            "unused_definitions": [
                {"file": d.rel_path, "line": d.lineno, "kind": d.kind, "name": d.name}
                for d in report.unused_definitions
            ],
        }
        state.output.emit_json(payload)
        cache_output("deadcode", proj.name, payload)
    else:
        if not report.total:
            state.output.print(f"[green]No unused imports or definitions found in '{proj.name}'.[/green]")
        else:
            if report.unused_imports:
                render_table(
                    state.output,
                    f"{proj.name} — unused imports",
                    ["file", "line", "name"],
                    [[i.rel_path, i.lineno, i.name] for i in report.unused_imports],
                )
            if report.unused_definitions:
                render_table(
                    state.output,
                    f"{proj.name} — unused functions/classes",
                    ["file", "line", "kind", "name"],
                    [[d.rel_path, d.lineno, d.kind, d.name] for d in report.unused_definitions],
                )
            state.output.warn(
                f"{report.total} potential dead-code finding(s) — verify before deleting; "
                "dynamic dispatch/reflection can cause false positives."
            )
        cache_output(
            "deadcode",
            proj.name,
            {
                "unused_imports": [{"file": i.rel_path, "name": i.name} for i in report.unused_imports],
                "unused_definitions": [{"file": d.rel_path, "name": d.name} for d in report.unused_definitions],
            },
        )

    if ci and report.total:
        state.exit_code = CHECK_FAILED
        raise typer.Exit(code=CHECK_FAILED)
