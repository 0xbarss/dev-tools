"""`devtools clean` — safe cleanup of __pycache__, node_modules, build/, dist/,
cache files (spec §6). Always prints a size report before deleting; requires
confirmation unless --yes.
"""

from __future__ import annotations

import shutil
from typing import Optional

import typer

from devtools.commands._shared import resolve_project
from devtools.core.clean_engine import filter_older_than, find_candidates, total_size
from devtools.core.output import render_table
from devtools.utils.helpers import ParseError, cutoff_datetime, human_size

app = typer.Typer()


@app.command()
def clean(
    ctx: typer.Context,
    project: Optional[str] = typer.Argument(None, help="Project to clean."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be deleted without deleting anything."),
    older_than: Optional[str] = typer.Option(None, "--older-than", help="Only remove candidates older than this, e.g. 30d."),
    yes: bool = typer.Option(False, "--yes", help="Skip the confirmation prompt."),
) -> None:
    """Remove build/cache junk (__pycache__, node_modules, build/, dist/, etc.)."""
    state = ctx.obj
    proj = resolve_project(ctx, project)

    candidates = find_candidates(proj.resolved_path)
    if older_than:
        try:
            cutoff = cutoff_datetime(older_than)
        except ParseError as exc:
            state.output.error(str(exc))
            raise typer.Exit(code=2)
        candidates = filter_older_than(candidates, cutoff)

    if not candidates:
        state.output.print(f"Nothing to clean in '{proj.name}'.")
        return

    rows = [[c.rel_path, "dir" if c.is_dir else "file", human_size(c.size)] for c in candidates]
    render_table(state.output, f"{proj.name} — clean candidates", ["path", "type", "size"], rows)
    state.output.print(f"Total: {human_size(total_size(candidates))} across {len(candidates)} item(s).")

    if dry_run:
        state.output.print("[dim]--dry-run: nothing was deleted.[/dim]")
        return

    if not yes:
        confirmed = typer.confirm(f"Delete {len(candidates)} item(s) totaling {human_size(total_size(candidates))}?")
        if not confirmed:
            state.output.print("Aborted; nothing was deleted.")
            return

    removed = 0
    for c in candidates:
        try:
            if c.is_dir:
                shutil.rmtree(c.path, ignore_errors=True)
            else:
                c.path.unlink(missing_ok=True)
            removed += 1
        except OSError as exc:
            state.output.warn(f"Could not remove {c.rel_path}: {exc}")

    state.output.print(f"[green]Removed {removed} item(s).[/green]")
