"""`devtools daemon` — run `devtools watch` detached in the background
(backlog #51, P3): start it once, close your terminal, `status`/`stop`
it later. One daemon per project.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

import typer

from devtools.commands._shared import fail, resolve_project
from devtools.core.daemon_engine import DaemonError, start as start_daemon, status as daemon_status, stop as stop_daemon, tail_log
from devtools.core.exit_codes import GENERAL_ERROR, INVALID_USAGE
from devtools.core.output import render_kv

app = typer.Typer(help="Run `devtools watch` detached in the background.")


@app.command("start")
def start(
    ctx: typer.Context,
    command: str = typer.Argument(..., help="devtools command to watch, e.g. doctor, lint, health."),
    project: Optional[str] = typer.Argument(None, help="Project to watch (defaults to the configured project)."),
    interval: float = typer.Option(5.0, "--interval", help="Polling interval in seconds."),
    arg: List[str] = typer.Option([], "--arg", help="Extra flag to pass through to the watched command (repeatable)."),
) -> None:
    """Start a background daemon that re-runs `devtools <command>` on
    file change, logging to the daemon's own log file."""
    state = ctx.obj
    proj = resolve_project(ctx, project)

    try:
        result = start_daemon(proj.name, proj.resolved_path, command, interval=interval, extra_args=list(arg))
    except DaemonError as exc:
        fail(ctx, INVALID_USAGE, str(exc))
        return

    if state.output.is_json:
        state.output.emit_json({"project": proj.name, "pid": result.pid, "log_path": str(result.log_path)})
        return
    state.output.print(f"[green]Started daemon for '{proj.name}'[/green] (pid {result.pid}), watching `{command}` every {interval}s.")
    state.output.print(f"Logs: {result.log_path}")


@app.command("stop")
def stop(ctx: typer.Context, project: Optional[str] = typer.Argument(None, help="Project whose daemon to stop.")) -> None:
    """Stop a running daemon (SIGTERM, then SIGKILL after a short grace period)."""
    state = ctx.obj
    proj = resolve_project(ctx, project)
    stopped = stop_daemon(proj.name)
    if not stopped:
        fail(ctx, GENERAL_ERROR, f"No daemon is running for '{proj.name}'.")
        return
    state.output.print(f"[green]Stopped daemon for '{proj.name}'.[/green]")


@app.command("status")
def status_cmd(
    ctx: typer.Context,
    project: Optional[str] = typer.Argument(None, help="Project to check."),
    logs: int = typer.Option(0, "--logs", help="Also print the last N lines of the daemon's log."),
) -> None:
    """Show whether a daemon is running for a project, its pid, and uptime."""
    state = ctx.obj
    proj = resolve_project(ctx, project)
    result = daemon_status(proj.name)

    if state.output.is_json:
        payload = {"project": proj.name, "running": result.running, "pid": result.pid, "started_at": result.started_at}
        if logs and result.running:
            payload["logs"] = tail_log(proj.name, logs)
        state.output.emit_json(payload)
        return

    if not result.running:
        state.output.print(f"[dim]No daemon running for '{proj.name}'.[/dim]")
        return

    started = datetime.fromtimestamp(result.started_at).isoformat(timespec="seconds") if result.started_at else "unknown"
    render_kv(state.output, f"Daemon status — {proj.name}", {"running": True, "pid": result.pid, "started_at": started, "log_path": str(result.log_path)})
    if logs:
        for line in tail_log(proj.name, logs):
            print(line)
