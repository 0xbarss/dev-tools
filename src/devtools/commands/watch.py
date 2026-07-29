"""`devtools watch` — re-run a command on file change (backlog #39). Stays
thin per the existing `commands/` convention; the polling/change-detection
logic lives in `core/watch_engine.py`. This module is the one place that
needs to invoke another `devtools` command *from inside* a command, so the
import of the root Typer `app` is deliberately local to the function body
to avoid a circular import with `cli.py` (which imports this module)."""

from __future__ import annotations

from typing import List, Optional

import typer

from devtools.commands._shared import build_ignore_rules, resolve_project
from devtools.core.watch_engine import watch_loop

app = typer.Typer()


@app.command()
def watch(
    ctx: typer.Context,
    command: str = typer.Argument(..., help="devtools command to re-run on change, e.g. stats, doctor, lint, health."),
    project: Optional[str] = typer.Argument(None, help="Project to watch."),
    interval: float = typer.Option(2.0, "--interval", help="Polling interval in seconds."),
    arg: List[str] = typer.Option([], "--arg", help="Extra flag to pass through to the watched command (repeatable), e.g. --arg --ci."),
    once: bool = typer.Option(False, "--once", help="Run the command once and exit, instead of watching for changes."),
    max_iterations: Optional[int] = typer.Option(
        None, "--max-iterations", hidden=True, help="Internal/testing: stop polling after N iterations instead of running forever."
    ),
) -> None:
    """Re-run `devtools <command> <project>` every time a tracked file
    changes -- e.g. `devtools watch doctor` while you clean up a repo, or
    `devtools watch lint --arg --fix` while refactoring. Stop with
    Ctrl+C."""
    state = ctx.obj
    proj = resolve_project(ctx, project)
    rules = build_ignore_rules(ctx, proj)

    from devtools.cli import app as root_app  # local: avoids a cli.py <-> commands.watch import cycle

    invoke_args = [command, proj.name, *arg]

    def run_once(initial: bool) -> None:
        label = "Running" if initial else "Change detected -- re-running"
        state.output.print(f"\n[bold cyan]{label}: devtools {' '.join(invoke_args)}[/bold cyan]\n")
        try:
            root_app(invoke_args, standalone_mode=False)
        except SystemExit:
            pass  # a failing exit code from the watched command shouldn't kill the watch loop itself
        except Exception as exc:  # noqa: BLE001 - surface it and keep watching, don't crash the loop
            state.output.error(f"devtools {command} raised: {exc}")

    if once:
        run_once(initial=True)
        return

    state.output.print(f"[dim]Watching '{proj.name}' (polling every {interval}s) -- press Ctrl+C to stop.[/dim]")
    try:
        watch_loop(proj.resolved_path, rules, run_once, poll_interval=interval, max_iterations=max_iterations)
    except KeyboardInterrupt:
        state.output.print("\n[dim]Stopped watching.[/dim]")