"""`devtools search` — concept search, keyword or semantic (spec §6; proposal
deep-dive #2 for `--semantic`).

Default mode: keyword/synonym expansion + grep under the hood. `--semantic`
ranks by cosine similarity over a local TF-IDF index (`--build-index`),
falling back to keyword search with a warning if no index exists yet.
"""

from __future__ import annotations

from typing import Optional

import typer

from devtools.commands._shared import build_ignore_rules, fail, resolve_project
from devtools.core.exit_codes import GENERAL_ERROR
from devtools.core.export_engine import cache_output
from devtools.core.fzf_integration import NOT_INSTALLED_HINT, run_fzf
from devtools.core.output import render_table
from devtools.core.search_engine import build_index as build_index_fn, semantic_search, search as search_engine

app = typer.Typer()


@app.command()
def search(
    ctx: typer.Context,
    project: Optional[str] = typer.Argument(None, help="Project to search."),
    concept: Optional[str] = typer.Argument(None, help="Concept to search for, e.g. authentication, database, payment, cache, jwt, endpoint."),
    build_index: bool = typer.Option(False, "--build-index", help="Build/refresh the local TF-IDF index used by --semantic."),
    semantic: bool = typer.Option(False, "--semantic", help="Rank by meaning (cosine similarity over the local index) instead of keyword overlap."),
    fzf: bool = typer.Option(False, "--fzf", help="Pick results interactively via fzf (falls back to normal output if fzf isn't installed)."),
) -> None:
    """Search a project by concept rather than literal string."""
    state = ctx.obj
    proj = resolve_project(ctx, project)
    rules = build_ignore_rules(ctx, proj)

    if build_index:
        try:
            count = build_index_fn(proj.resolved_path, proj.name, rules)
        except Exception as exc:  # defensive: indexing should never crash the CLI
            fail(ctx, GENERAL_ERROR, f"Failed to build index: {exc}")
        state.output.print(f"[green]Indexed {count} changed file(s) for '{proj.name}'.[/green]")
        return

    if not concept:
        fail(ctx, GENERAL_ERROR, "A concept argument is required unless --build-index is passed.")

    if semantic:
        hits, used_semantic = semantic_search(proj.resolved_path, proj.name, concept, ignore_rules=rules)
        if not used_semantic:
            state.output.warn(
                f"No semantic index found for '{proj.name}' -- falling back to keyword search. "
                "Run `devtools search --build-index` first for true semantic ranking."
            )
            hits = search_engine(proj.resolved_path, rules, concept)
    else:
        hits = search_engine(proj.resolved_path, rules, concept)

    if state.output.is_json:
        payload = [
            {
                "path": h.rel_path,
                "score": h.score,
                "matched_terms": h.matched_terms,
                "sample_lines": [{"line": m.line_number, "text": m.line} for m in h.sample_matches],
            }
            for h in hits
        ]
        state.output.emit_json(payload)
        cache_output("search", proj.name, payload)
        return

    if not hits:
        state.output.print(f"No matches for concept '{concept}' in '{proj.name}'.")
        return

    if fzf:
        candidates = [f"{h.rel_path} ({h.score}): {', '.join(h.matched_terms)}" for h in hits]
        selected = run_fzf(candidates, prompt=f"{concept} > ")
        if selected is None:
            state.output.print(f"[dim]{NOT_INSTALLED_HINT}[/dim]")
        else:
            selected_set = set(selected)
            hits = [h for h, c in zip(hits, candidates) if c in selected_set]
            if not hits:
                return

    rows = [[h.rel_path, h.score, ", ".join(h.matched_terms)] for h in hits]
    render_table(state.output, f"'{concept}' — related files", ["path", "score", "matched terms"], rows)
    cache_output("search", proj.name, {"concept": concept, "hit_count": len(hits)})
