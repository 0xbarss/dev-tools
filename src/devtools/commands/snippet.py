"""`devtools snippet` — a small, global library of reusable code snippets
(Prioritized Backlog: "Snippet manager", P3).
"""

from __future__ import annotations

import sys

import typer

from devtools.commands._shared import fail
from devtools.core.exit_codes import INVALID_USAGE, PROJECT_NOT_FOUND
from devtools.core.output import render_table
from devtools.core.snippet_store import add_snippet, load_snippets, remove_snippet, search_snippets

app = typer.Typer(help="A small, global library of reusable code snippets.")


@app.command("add")
def add(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Short name for this snippet, e.g. 'retry-decorator'."),
    content: str = typer.Argument(None, help="The snippet body. If omitted, reads from stdin."),
    language: str = typer.Option("", "--language", "-l", help="Language tag, e.g. 'python' (for display/highlighting only)."),
    tags: str = typer.Option("", "--tags", help="Comma-separated tags, e.g. 'logging,boilerplate'."),
) -> None:
    """Save a snippet. Pass the content as an argument, or pipe it in:
    `cat retry.py | devtools snippet add retry-decorator`."""
    state = ctx.obj
    if content is None:
        if sys.stdin.isatty():
            fail(ctx, INVALID_USAGE, "No content given. Pass it as an argument or pipe it via stdin.")
        content = sys.stdin.read()
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    add_snippet(name, content, language=language, tags=tag_list)
    state.output.print(f"[green]Saved snippet '{name}'[/green]")


@app.command("list")
def list_snippets(ctx: typer.Context) -> None:
    """List all saved snippets."""
    state = ctx.obj
    snippets = load_snippets()
    rows = [[s.name, s.language, ", ".join(s.tags)] for s in sorted(snippets.values(), key=lambda s: s.name)]
    render_table(state.output, "Snippets", ["name", "language", "tags"], rows, json_key="snippets")


@app.command("show")
def show(ctx: typer.Context, name: str = typer.Argument(...)) -> None:
    """Print a saved snippet's content."""
    state = ctx.obj
    snippets = load_snippets()
    snippet = snippets.get(name)
    if snippet is None:
        fail(ctx, PROJECT_NOT_FOUND, f"No snippet named '{name}'. Run `devtools snippet list` to see saved snippets.")
    if state.output.is_json:
        state.output.emit_json({"name": snippet.name, "language": snippet.language, "tags": snippet.tags, "content": snippet.content})
    else:
        print(snippet.content)


@app.command("search")
def search(ctx: typer.Context, query: str = typer.Argument(...)) -> None:
    """Search snippet names, tags, and content for a substring."""
    state = ctx.obj
    hits = search_snippets(query)
    rows = [[s.name, s.language, ", ".join(s.tags)] for s in hits]
    render_table(state.output, f"Snippets matching '{query}'", ["name", "language", "tags"], rows, json_key="snippets")


@app.command("remove")
def remove(ctx: typer.Context, name: str = typer.Argument(...)) -> None:
    """Delete a saved snippet."""
    state = ctx.obj
    if remove_snippet(name):
        state.output.print(f"Removed snippet '{name}'")
    else:
        fail(ctx, PROJECT_NOT_FOUND, f"No snippet named '{name}'.")
