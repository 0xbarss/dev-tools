"""`devtools doctor` — repository health checks (spec §6)."""

from __future__ import annotations

from typing import Optional

import typer

from devtools.commands._shared import build_ignore_rules, fail, resolve_project
from devtools.core.doctor_checks import apply_fixes, run_all_checks
from devtools.core.exit_codes import CHECK_FAILED, INVALID_USAGE
from devtools.core.export_engine import cache_output
from devtools.core.notify_engine import load_targets, send_notification
from devtools.core.output import render_table

app = typer.Typer()

_SEVERITY_STYLE = {"error": "bold red", "warning": "yellow", "info": "dim"}


@app.command()
def doctor(
    ctx: typer.Context,
    project: Optional[str] = typer.Argument(None, help="Project to check."),
    fix: bool = typer.Option(False, "--fix", help="Apply auto-fixable issues (e.g. add missing .gitignore entries)."),
    ci: bool = typer.Option(False, "--ci", help="Exit 5 on any failed check; never prompt."),
    notify: Optional[str] = typer.Option(None, "--notify", help="Send a summary to this configured `devtools notify` target, but only if issues were found."),
) -> None:
    """Run repository health checks: README/LICENSE, tests, binaries, symlinks, duplicates, .gitignore."""
    state = ctx.obj
    proj = resolve_project(ctx, project)
    rules = build_ignore_rules(ctx, proj)
    ignored_dirs = state.settings.ignored_dirs_for(proj.name)

    issues = run_all_checks(proj.resolved_path, rules, ignored_dirs)

    actions: list[str] = []
    if fix:
        actions = apply_fixes(proj.resolved_path, issues, ignored_dirs, project_name=proj.name)
        if actions:
            rules = build_ignore_rules(ctx, proj)
            issues = run_all_checks(proj.resolved_path, rules, ignored_dirs)

    if state.output.is_json:
        payload = {
            "issues": [
                {"check": i.check, "severity": i.severity, "message": i.message, "fixable": i.fixable} for i in issues
            ],
            "fixes_applied": actions,
        }
        state.output.emit_json(payload)
        cache_output("doctor", proj.name, payload)
    else:
        if not issues:
            state.output.print(f"[green]No issues found in '{proj.name}'.[/green]")
        else:
            rows = [[i.severity, i.check, i.message] for i in issues]
            render_table(state.output, f"{proj.name} — doctor report", ["severity", "check", "message"], rows)
        for action in actions:
            state.output.print(f"[green]Fixed:[/green] {action}")
        cache_output(
            "doctor",
            proj.name,
            {"issues": [{"check": i.check, "severity": i.severity, "message": i.message} for i in issues]},
        )

    if notify is not None and issues:
        targets = load_targets()
        target = targets.get(notify)
        if target is None:
            fail(ctx, INVALID_USAGE, f"No notification target named '{notify}'. Run `devtools notify list`.")
        errors = sum(1 for i in issues if i.severity == "error")
        send_notification(
            target,
            event="devtools doctor",
            message=f"doctor found {len(issues)} issue(s) ({errors} error-severity) in '{proj.name}'.",
            fields={"project": proj.name, "issues": len(issues), "errors": errors},
        )

    if ci and issues:
        state.exit_code = CHECK_FAILED
        raise typer.Exit(code=CHECK_FAILED)