"""`devtools alias` — user-defined shortcuts for common command chains (spec §7)."""

from __future__ import annotations

import subprocess
import sys

import typer

from devtools.commands._shared import fail
from devtools.core.alias_store import add_alias, load_aliases, remove_alias, split_chain
from devtools.core.exit_codes import GENERAL_ERROR, PROJECT_NOT_FOUND
from devtools.core.output import render_table

app = typer.Typer(help="User-defined shortcuts for common command chains.")


@app.command("add")
def add(ctx: typer.Context, name: str = typer.Argument(...), command: str = typer.Argument(..., help='e.g. "stats api && doctor api"')) -> None:
    """Save a named shortcut for a chain of devtools commands."""
    state = ctx.obj
    add_alias(name, command)
    state.output.print(f"[green]Saved alias '{name}' -> {command}[/green]")


@app.command("remove")
def remove(ctx: typer.Context, name: str = typer.Argument(...)) -> None:
    """Delete a saved alias."""
    state = ctx.obj
    if remove_alias(name):
        state.output.print(f"Removed alias '{name}'")
    else:
        fail(ctx, PROJECT_NOT_FOUND, f"No alias named '{name}'.")


@app.command("list")
def list_aliases(ctx: typer.Context) -> None:
    """List all saved aliases."""
    state = ctx.obj
    aliases = load_aliases()
    rows = [[name, command] for name, command in sorted(aliases.items())]
    render_table(state.output, "Aliases", ["name", "command"], rows, json_key="aliases")


@app.command("run")
def run(ctx: typer.Context, name: str = typer.Argument(...)) -> None:
    """Run a saved alias, executing each `&&`-separated devtools command in order."""
    state = ctx.obj
    aliases = load_aliases()
    if name not in aliases:
        fail(ctx, PROJECT_NOT_FOUND, f"No alias named '{name}'. Run `devtools alias list` to see saved aliases.")

    for argv in split_chain(aliases[name]):
        state.output.print(f"[bold]$ devtools {' '.join(argv)}[/bold]")
        result = subprocess.run([sys.executable, "-m", "devtools.cli", *argv])
        if result.returncode != 0:
            fail(ctx, GENERAL_ERROR, f"Alias '{name}' stopped: `devtools {' '.join(argv)}` exited {result.returncode}.")
