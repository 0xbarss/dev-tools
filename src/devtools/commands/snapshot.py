"""`devtools snapshot` — save/restore a lightweight workspace session
(backlog #32, P2): the git branch, a list of files you were working with,
and free-form notes, under a name you choose. Restoring never touches
your working tree by default (`git checkout` is opt-in via
`--checkout`) -- this is a memory aid, not an automation that could
surprise you mid-task.
"""

from __future__ import annotations

from typing import List, Optional

import typer

from devtools.commands._shared import fail, resolve_project
from devtools.core.exit_codes import GENERAL_ERROR, INVALID_USAGE
from devtools.core.output import render_kv, render_table
from devtools.core.snapshot_store import load_snapshots, remove_snapshot, save_snapshot
from devtools.utils.git import GitError, current_branch

app = typer.Typer(help="Save/restore a lightweight workspace session (branch, files, notes).")


@app.command("save")
def save(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Name to save this snapshot under."),
    project: Optional[str] = typer.Option(None, "--project", help="Project this snapshot belongs to (defaults to the configured project)."),
    file: List[str] = typer.Option([], "--file", help="A file you're working on worth remembering (repeatable)."),
    note: str = typer.Option("", "--note", help="Free-form note, e.g. what you were doing / where you left off."),
) -> None:
    """Save the current branch + a list of files + a note under `name`."""
    state = ctx.obj
    proj = resolve_project(ctx, project)

    branch = None
    try:
        branch = current_branch(proj.resolved_path)
    except GitError:
        pass  # not a git repo, or detached -- branch is just optional context

    snapshot = save_snapshot(name, project=proj.name, branch=branch, files=file, note=note)

    if state.output.is_json:
        state.output.emit_json({"name": name, **snapshot.to_dict()})
        return
    state.output.print(f"[green]Saved snapshot '{name}'[/green] ({proj.name}, branch={branch or 'n/a'}, {len(file)} file(s))")


@app.command("restore")
def restore(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Snapshot to restore."),
    checkout: bool = typer.Option(False, "--checkout", help="Also `git checkout` the saved branch (off by default -- restoring only prints information otherwise)."),
) -> None:
    """Show (and optionally check out the branch of) a saved snapshot."""
    state = ctx.obj
    snapshots = load_snapshots()
    snapshot = snapshots.get(name)
    if snapshot is None:
        fail(ctx, INVALID_USAGE, f"No snapshot named '{name}'. Run `devtools snapshot list` to see saved snapshots.")
        return

    if checkout:
        if not snapshot.branch:
            fail(ctx, GENERAL_ERROR, f"Snapshot '{name}' has no recorded branch to check out.")
            return
        proj = resolve_project(ctx, snapshot.project)
        from devtools.utils import git as gitutil

        try:
            gitutil.checkout_branch(proj.resolved_path, snapshot.branch)
        except GitError as exc:
            fail(ctx, GENERAL_ERROR, str(exc))
            return
        state.output.print(f"[green]Checked out '{snapshot.branch}'[/green]")

    if state.output.is_json:
        state.output.emit_json({"name": name, **snapshot.to_dict()})
        return

    render_kv(
        state.output,
        f"Snapshot '{name}'",
        {
            "project": snapshot.project,
            "branch": snapshot.branch or "(none recorded)",
            "note": snapshot.note or "(none)",
            "created_at": snapshot.created_at,
            "files": ", ".join(snapshot.files) if snapshot.files else "(none)",
        },
    )


@app.command("list")
def list_snapshots(ctx: typer.Context) -> None:
    """List all saved snapshots."""
    state = ctx.obj
    snapshots = load_snapshots()
    rows = [[s.name, s.project, s.branch or "", s.note, s.created_at] for s in snapshots.values()]

    if state.output.is_json:
        state.output.emit_json({"snapshots": [{"name": s.name, **s.to_dict()} for s in snapshots.values()]})
        return
    if not rows:
        state.output.print("[dim]No snapshots saved yet. Try `devtools snapshot save <name>`.[/dim]")
        return
    render_table(state.output, "Snapshots", ["name", "project", "branch", "note", "created_at"], rows)


@app.command("remove")
def remove(ctx: typer.Context, name: str = typer.Argument(..., help="Snapshot to remove.")) -> None:
    """Delete a saved snapshot."""
    state = ctx.obj
    if not remove_snapshot(name):
        fail(ctx, INVALID_USAGE, f"No snapshot named '{name}'.")
        return
    state.output.print(f"[green]Removed snapshot '{name}'[/green]")
