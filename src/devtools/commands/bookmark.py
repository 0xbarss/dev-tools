"""`devtools bookmark` — named quick-jumps to paths within a project
(Prioritized Backlog: "Bookmarks", P3).

A shell can't `cd` on behalf of its child process, so `bookmark go` doesn't
try to be a `cd` replacement -- it just prints the bookmark's absolute path
so it composes naturally with `cd $(devtools bookmark go name)` or an
editor invocation like `$EDITOR $(devtools bookmark go name)`.
"""

from __future__ import annotations

import typer

from devtools.commands._shared import fail, resolve_project
from devtools.core.bookmark_store import add_bookmark, load_bookmarks, remove_bookmark
from devtools.core.exit_codes import PROJECT_NOT_FOUND
from devtools.core.output import render_table

app = typer.Typer(help="Named quick-jumps to paths within your projects.")


@app.command("add")
def add(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Short name for this bookmark, e.g. 'api-config'."),
    path: str = typer.Argument(..., help="Path within the project, relative or absolute."),
    project: str = typer.Option(None, "--project", help="Project the path belongs to (defaults to the configured project)."),
    note: str = typer.Option("", "--note", help="Optional reminder of why this path matters."),
) -> None:
    """Save a named bookmark pointing at a path inside a project."""
    state = ctx.obj
    proj = resolve_project(ctx, project)
    rel_path = _relative_to_project(path, proj)
    add_bookmark(name, proj.name, rel_path, note=note)
    state.output.print(f"[green]Bookmarked '{name}' -> {proj.name}:{rel_path}[/green]")


@app.command("list")
def list_bookmarks(ctx: typer.Context) -> None:
    """List all saved bookmarks."""
    state = ctx.obj
    bookmarks = load_bookmarks()
    rows = [[b.name, b.project, b.path, b.note] for b in sorted(bookmarks.values(), key=lambda b: b.name)]
    render_table(state.output, "Bookmarks", ["name", "project", "path", "note"], rows, json_key="bookmarks")


@app.command("remove")
def remove(ctx: typer.Context, name: str = typer.Argument(...)) -> None:
    """Delete a saved bookmark."""
    state = ctx.obj
    if remove_bookmark(name):
        state.output.print(f"Removed bookmark '{name}'")
    else:
        fail(ctx, PROJECT_NOT_FOUND, f"No bookmark named '{name}'.")


@app.command("go")
def go(ctx: typer.Context, name: str = typer.Argument(...)) -> None:
    """Print the absolute path for a bookmark (for use with $(...) / backticks)."""
    state = ctx.obj
    bookmarks = load_bookmarks()
    bookmark = bookmarks.get(name)
    if bookmark is None:
        fail(ctx, PROJECT_NOT_FOUND, f"No bookmark named '{name}'. Run `devtools bookmark list` to see saved bookmarks.")
    proj = state.projects.get(bookmark.project)
    if proj is None:
        fail(ctx, PROJECT_NOT_FOUND, f"Bookmark '{name}' points at project '{bookmark.project}', which is no longer registered.")
    absolute = (proj.resolved_path / bookmark.path).resolve()
    if state.output.is_json:
        state.output.emit_json({"name": name, "project": bookmark.project, "path": str(absolute)})
    else:
        print(str(absolute))


def _relative_to_project(path: str, project) -> str:
    from pathlib import Path

    p = Path(path)
    if p.is_absolute():
        try:
            return str(p.resolve().relative_to(project.resolved_path.resolve()))
        except ValueError:
            return str(p)
    return path
