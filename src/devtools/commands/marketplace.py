"""`devtools marketplace` — a listing page for community plugins/checks
(Prioritized Backlog: "Marketplace listing page", P2)."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from devtools.commands._shared import fail
from devtools.core.exit_codes import INVALID_USAGE
from devtools.core.marketplace_engine import (
    add_custom_entry,
    generate_site,
    load_registry,
    remove_custom_entry,
)
from devtools.core.output import render_table

app = typer.Typer(help="Browse and publish a listing of community devtools plugins/checks.")


@app.command("list")
def list_entries(
    ctx: typer.Context,
    category: Optional[str] = typer.Option(None, "--category", help="Filter to a single category."),
) -> None:
    """List curated and locally-registered marketplace entries."""
    state = ctx.obj
    registry = load_registry()
    entries = registry.entries
    if category:
        entries = [e for e in entries if e.category == category]

    if state.output.is_json:
        state.output.emit_json([e.to_dict() for e in entries])
        return

    if not entries:
        state.output.print("No marketplace entries found." + (f" (category: {category})" if category else ""))
        return

    rows = [[e.name, e.category, e.author, e.source, e.description] for e in entries]
    render_table(state.output, "devtools marketplace", ["name", "category", "author", "source", "description"], rows)


@app.command("add")
def add(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Plugin/check name."),
    description: str = typer.Argument(..., help="One-line description."),
    category: str = typer.Option("uncategorized", "--category"),
    author: str = typer.Option("you", "--author"),
    url: str = typer.Option("", "--url", help="Link to the plugin/check's source or docs."),
) -> None:
    """Register a local marketplace entry (stored alongside your config,
    not published anywhere — there's no hosted marketplace yet)."""
    state = ctx.obj
    add_custom_entry(name, description, category=category, author=author, url=url)
    state.output.print(f"[green]Added '{name}' to your local marketplace listing.[/green]")


@app.command("remove")
def remove(ctx: typer.Context, name: str = typer.Argument(...)) -> None:
    """Remove a locally-registered marketplace entry (curated entries can't be removed)."""
    state = ctx.obj
    if not remove_custom_entry(name):
        fail(ctx, INVALID_USAGE, f"No custom marketplace entry named '{name}' (curated entries can't be removed).")
    state.output.print(f"Removed '{name}'.")


@app.command("generate")
def generate(
    ctx: typer.Context,
    output: Path = typer.Option(Path("devtools-marketplace.html"), "--output", "-o", help="Where to write the static HTML page."),
) -> None:
    """Render the marketplace listing to a self-contained static HTML page."""
    state = ctx.obj
    written = generate_site(output)
    state.output.print(f"[green]Wrote marketplace listing page to {written}[/green]")