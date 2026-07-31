"""`devtools index` — persistent SQLite project index (proposal deep-dive #1).

Every command currently re-walks the filesystem; building an index once
turns future lookups near-instant and is the prerequisite for `search
--semantic`. Incremental by default (backlog #50): unchanged files (by
mtime) are left alone on rebuild.
"""

from __future__ import annotations

from typing import Optional

import typer

from typing import List

from devtools.commands._shared import build_ignore_rules, resolve_project
from devtools.core import index_engine, rag_index
from devtools.core.output import render_kv

app = typer.Typer(help="Build and inspect the local project index.")


@app.command("build")
def build(
    ctx: typer.Context,
    project: Optional[str] = typer.Argument(None, help="Project to index."),
    vectors: bool = typer.Option(False, "--vectors", help="Also build the TF-IDF vectors used by `search --semantic`."),
    full: bool = typer.Option(False, "--full", help="Force a full rebuild instead of the default incremental one."),
    rag: bool = typer.Option(
        False, "--rag",
        help="Build the persistent chunk-level RAG index used by `devtools ask` (proposal #25), "
        "instead of the whole-file index.",
    ),
    lang: List[str] = typer.Option([], "--lang", help="With --rag: restrict indexing to these languages (repeatable)."),
) -> None:
    """Build or refresh the project's SQLite index."""
    state = ctx.obj
    proj = resolve_project(ctx, project)
    rules = build_ignore_rules(ctx, proj)

    if rag:
        stats = rag_index.build(
            proj.resolved_path, proj.name, rules, languages=list(lang) or None, incremental=not full,
        )
        if state.output.is_json:
            state.output.emit_json(
                {
                    "project": proj.name,
                    "files_indexed": stats.files_indexed,
                    "files_changed": stats.files_changed,
                    "chunks_indexed": stats.chunks_indexed,
                }
            )
        else:
            state.output.print(
                f"[green]Built RAG index for '{proj.name}': {stats.chunks_indexed} chunk(s) "
                f"across {stats.files_indexed} file(s) ({stats.files_changed} changed).[/green]"
            )
        return

    changed = index_engine.build(proj.resolved_path, proj.name, rules, with_vectors=vectors, incremental=not full)

    if state.output.is_json:
        state.output.emit_json({"project": proj.name, "files_changed": changed, "vectors": vectors})
    else:
        state.output.print(f"[green]Indexed '{proj.name}': {changed} file(s) (re)written.[/green]")


@app.command("status")
def status(
    ctx: typer.Context,
    project: Optional[str] = typer.Argument(None, help="Project to check."),
    rag: bool = typer.Option(False, "--rag", help="Show status of the RAG chunk index instead of the whole-file index."),
) -> None:
    """Show index freshness and size for a project."""
    state = ctx.obj
    proj = resolve_project(ctx, project)
    rules = build_ignore_rules(ctx, proj)

    if rag:
        stats = rag_index.get_stats(proj.name)
        fresh = rag_index.is_fresh(proj.resolved_path, proj.name, rules)
        data = {
            "files_indexed": stats.file_count,
            "chunks_indexed": stats.chunk_count,
            "built_at": stats.built_at,
            "fresh": fresh,
        }
        render_kv(state.output, f"{proj.name} — RAG index status", data)
        return

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
def clear(
    ctx: typer.Context,
    project: Optional[str] = typer.Argument(None, help="Project whose index should be deleted."),
    rag: bool = typer.Option(False, "--rag", help="Delete the RAG chunk index instead of the whole-file index."),
) -> None:
    """Delete a project's index (e.g. before a clean --full rebuild)."""
    state = ctx.obj
    proj = resolve_project(ctx, project)
    deleted = rag_index.delete_index(proj.name) if rag else index_engine.delete_index(proj.name)
    label = "RAG index" if rag else "index"
    if state.output.is_json:
        state.output.emit_json({"project": proj.name, "deleted": deleted, "rag": rag})
    else:
        msg = f"Deleted {label} for '{proj.name}'." if deleted else f"No {label} existed for '{proj.name}'."
        state.output.print(f"[green]{msg}[/green]" if deleted else f"[dim]{msg}[/dim]")
