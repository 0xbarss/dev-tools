"""`devtools run` — a task-runner front-end (backlog #40, P2): finds
`<task>` across Makefile/npm scripts/justfile so you don't have to
remember which one this repo uses.
"""

from __future__ import annotations

from typing import Optional

import typer

from devtools.commands._shared import fail, resolve_project
from devtools.core.exit_codes import GENERAL_ERROR, INVALID_USAGE
from devtools.core.output import render_table
from devtools.core.task_runner_engine import discover_tasks, find_task, run_task

app = typer.Typer()


@app.command("run")
def run(
    ctx: typer.Context,
    project: Optional[str] = typer.Argument(None, help="Project to run the task in (defaults to the configured project)."),
    task: Optional[str] = typer.Argument(None, help="Task name to run, e.g. test, build, lint."),
    list_: bool = typer.Option(False, "--list", help="List all discovered tasks instead of running one."),
    source: Optional[str] = typer.Option(None, "--source", help="Disambiguate when the same task name exists in more than one place: 'make', 'npm', or 'just'."),
) -> None:
    """Run a task by name, auto-detected from Makefile/package.json/justfile.
    Exits with the task's own exit code (so it composes with `&&`/CI)."""
    state = ctx.obj
    proj = resolve_project(ctx, project)
    root = proj.resolved_path

    if list_ or task is None:
        tasks = discover_tasks(root)
        if state.output.is_json:
            state.output.emit_json({"tasks": [{"name": t.name, "source": t.source, "command": t.command} for t in tasks]})
            return
        if not tasks:
            state.output.print("[dim]No tasks found (looked for Makefile, package.json scripts, justfile).[/dim]")
            return
        render_table(state.output, f"{proj.name} — tasks", ["name", "source", "command"], [[t.name, t.source, t.command] for t in tasks])
        return

    matches = find_task(root, task)
    if not matches:
        fail(ctx, INVALID_USAGE, f"No task named '{task}' found (looked for Makefile, package.json scripts, justfile). Run `devtools run --list` to see what's available.")
        return
    if source:
        matches = [m for m in matches if m.source == source]
        if not matches:
            fail(ctx, INVALID_USAGE, f"No task named '{task}' from source '{source}'.")
            return
    if len(matches) > 1:
        sources = ", ".join(f"{m.source} ({m.command})" for m in matches)
        fail(ctx, GENERAL_ERROR, f"'{task}' is ambiguous — found in more than one place: {sources}. Disambiguate with --source.")
        return

    chosen = matches[0]
    state.output.info(f"Running: {chosen.command}")
    exit_code = run_task(root, chosen)
    if exit_code != 0:
        state.exit_code = GENERAL_ERROR
        raise typer.Exit(code=exit_code)
