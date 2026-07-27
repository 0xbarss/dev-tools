"""`devtools history` — append-only log of past runs (spec §7)."""

from __future__ import annotations

from typing import Optional

import typer

from devtools.core.history_log import read_entries
from devtools.core.output import render_table

app = typer.Typer()


@app.command()
def history(
    ctx: typer.Context,
    project: Optional[str] = typer.Option(None, "--project", help="Only show runs for this project."),
    last: Optional[int] = typer.Option(None, "--last", help="Only show the most recent N runs."),
) -> None:
    """Show past devtools invocations: command, project, timestamp, duration, exit code."""
    state = ctx.obj
    entries = read_entries(project=project, last=last)

    if not entries:
        state.output.print("No history recorded yet.")
        return

    rows = [
        [e.get("ts", ""), e.get("cmd", ""), e.get("project") or "-", f"{e.get('duration_ms', 0)}ms", e.get("exit_code", "")]
        for e in entries
    ]
    render_table(state.output, "History", ["timestamp", "command", "project", "duration", "exit"], rows, json_key="history")