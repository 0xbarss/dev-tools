"""`devtools search` — semantic-ish concept search (spec §6, staged plan).

Phase 3 (current): keyword/synonym expansion + grep under the hood.
--build-index is reserved for the later, opt-in local-embedding stage.
"""

from __future__ import annotations

from typing import Optional

import typer

from devtools.commands._shared import build_ignore_rules, fail, resolve_project
from devtools.core.exit_codes import GENERAL_ERROR
from devtools.core.export_engine import cache_output
from devtools.core.fzf_integration import NOT_INSTALLED_HINT, run_fzf
from devtools.core.output import render_table
from devtools.core.search_engine import build_index, search as search_engine

app = typer.Typer()


@app.command()
def search(
    ctx: typer.Context,
    project: Optional[str] = typer.Argument(None, help="Project to search."),
    concept: str = typer.Argument(..., help="Concept to search for, e.g. authentication, database, payment, cache, jwt, endpoint."),
    build_index: bool = typer.Option(False, "--build-index", help="Build a local embedding index for true semantic ranking (not yet available)."),
    fzf: bool = typer.Option(False, "--fzf", help="Pick results interactively via fzf (falls back to normal output if fzf isn't installed)."),
) -> None:
    """Search a project by concept rather than literal string."""
    state = ctx.obj
    proj = resolve_project(ctx, project)

    if build_index:
        try:
            from devtools.core import search_engine as _se

            _se.build_index(proj.resolved_path)
        except NotImplementedError as exc:
            fail(ctx, GENERAL_ERROR, str(exc))
        return

    rules = build_ignore_rules(ctx, proj)
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