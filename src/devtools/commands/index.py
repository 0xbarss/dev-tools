"""`devtools index` — persistent SQLite project index (proposal deep-dive #1).

Every command currently re-walks the filesystem; building an index once
turns future lookups near-instant and is the prerequisite for `search
--semantic`. Incremental by default (backlog #50): unchanged files (by
mtime) are left alone on rebuild.
"""

from __future__ import annotations

from typing import Optional

import typer

from devtools.commands._shared import build_ignore_rules, resolve_project
from devtools.core import index_engine
from devtools.core.output import render_kv

app = typer.Typer(help="Build and inspect the local project index.")


@app.command("build")
def build(
    ctx: typer.Context,
    project: Optional[str] = typer.Argument(None, help="Project to index."),
    vectors: bool = typer.Option(False, "--vectors", help="Also build the TF-IDF vectors used by `search --semantic`."),
    full: bool = typer.Option(False, "--full", help="Force a full rebuild instead of the default incremental one."),
) -> None:
    """Build or refresh the project's SQLite index."""
    state = ctx.obj
    proj = resolve_project(ctx, project)
    rules = build_ignore_rules(ctx, proj)

    changed = index_engine.build(proj.resolved_path, proj.name, rules, with_vectors=vectors, incremental=not full)

    if state.output.is_json:
        state.output.emit_json({"project": proj.name, "files_changed": changed, "vectors": vectors})
    else:
        state.output.print(f"[green]Indexed '{proj.name}': {changed} file(s) (re)written.[/green]")


@app.command("status")
def status(ctx: typer.Context, project: Optional[str] = typer.Argument(None, help="Project to check.")) -> None:
    """Show index freshness and size for a project."""
    state = ctx.obj
    proj = resolve_project(ctx, project)
    rules = build_ignore_rules(ctx, proj)

    stats = index_engine.get_stats(proj.name)
    fresh = index_engine.is_fresh(proj.resolved_path, proj.name, rules)
    data = {
        "files_indexed": stats.file_count,
        "has_vectors": stats.has_vectors,
        "built_at": stats.built_at,
        "fresh": fresh,
    }
    render_kv(state.output, f"{proj.name} — index status", data)


@app.command("clear")
def clear(ctx: typer.Context, project: Optional[str] = typer.Argument(None, help="Project whose index should be deleted.")) -> None:
    """Delete a project's index (e.g. before a clean --full rebuild)."""
    state = ctx.obj
    proj = resolve_project(ctx, project)
    deleted = index_engine.delete_index(proj.name)
    if state.output.is_json:
        state.output.emit_json({"project": proj.name, "deleted": deleted})
    else:
        msg = f"Deleted index for '{proj.name}'." if deleted else f"No index existed for '{proj.name}'."
        state.output.print(f"[green]{msg}[/green]" if deleted else f"[dim]{msg}[/dim]")
