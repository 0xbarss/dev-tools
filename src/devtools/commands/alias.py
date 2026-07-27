"""`devtools alias` — user-defined shortcuts for common command chains (spec §7)."""

from __future__ import annotations

import subprocess
import sys

import typer

from devtools.commands._shared import fail
from devtools.core.alias_store import add_alias, load_aliases, parse_pipeline, remove_alias
from devtools.core.exit_codes import GENERAL_ERROR, PROJECT_NOT_FOUND
from devtools.core.output import render_table

app = typer.Typer(help="User-defined shortcuts for common command chains.")


@app.command("add")
def add(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    command: str = typer.Argument(..., help='e.g. "stats api && grep api TODO | wc -l"'),
) -> None:
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
    """Run a saved alias: `&&`-separated steps run in order (stopping on the
    first failure), and any `|`-connected commands within a step are piped
    together like a shell pipeline (each command's stdout feeds the next
    command's stdin)."""
    state = ctx.obj
    aliases = load_aliases()
    if name not in aliases:
        fail(ctx, PROJECT_NOT_FOUND, f"No alias named '{name}'. Run `devtools alias list` to see saved aliases.")

    for stages in parse_pipeline(aliases[name]):
        label = " | ".join("devtools " + " ".join(argv) for argv in stages)
        state.output.print(f"[bold]$ {label}[/bold]")
        returncode = _run_pipe_stages(stages)
        if returncode != 0:
            fail(ctx, GENERAL_ERROR, f"Alias '{name}' stopped: `{label}` exited {returncode}.")


def _run_pipe_stages(stages: list[list[str]]) -> int:
    """Run one or more devtools invocations connected by pipes.

    A single-stage step (no `|`) just runs normally with inherited
    stdout/stderr. Multiple stages are wired stdout->stdin like a shell
    pipeline; only the final stage's output goes to the terminal, matching
    normal shell-pipe semantics.
    """
    if len(stages) == 1:
        result = subprocess.run([sys.executable, "-m", "devtools.cli", *stages[0]])
        return result.returncode

    processes: list[subprocess.Popen] = []
    prev_stdout = None
    for i, argv in enumerate(stages):
        is_last = i == len(stages) - 1
        proc = subprocess.Popen(
            [sys.executable, "-m", "devtools.cli", *argv],
            stdin=prev_stdout,
            stdout=None if is_last else subprocess.PIPE,
        )
        if prev_stdout is not None:
            prev_stdout.close()
        processes.append(proc)
        prev_stdout = proc.stdout

    returncode = 0
    for proc in processes:
        proc.wait()
        if proc.returncode != 0:
            returncode = proc.returncode
    return returncode