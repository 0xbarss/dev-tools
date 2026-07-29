"""`devtools stats` — repository statistics (spec §6)."""

from __future__ import annotations

from typing import Optional

import typer

from devtools.commands._shared import build_ignore_rules, fail, resolve_project
from devtools.core import config as cfgmod
from devtools.core.exit_codes import GENERAL_ERROR
from devtools.core.export_engine import cache_output
from devtools.core.hotspots_engine import DEFAULT_SINCE, compute_hotspots
from devtools.core.output import render_kv, render_table
from devtools.core.stats_engine import compute_stats
from devtools.utils.git import GitError
from devtools.utils.helpers import human_size

app = typer.Typer()


@app.command()
def stats(
    ctx: typer.Context,
    project: Optional[str] = typer.Argument(None, help="Project to compute stats for."),
    top: int = typer.Option(10, "--top", help="How many largest files to show."),
    hotspots: bool = typer.Option(
        False, "--hotspots", help="Instead of the usual summary, rank files by churn x complexity (backlog #10)."
    ),
    since: str = typer.Option(DEFAULT_SINCE, "--since", help="Git-recognized date expression for the churn window (used with --hotspots)."),
) -> None:
    """Show file count, line count, language distribution, and largest files
    -- or, with --hotspots, the files most worth a refactor."""
    state = ctx.obj
    proj = resolve_project(ctx, project)
    rules = build_ignore_rules(ctx, proj)

    if hotspots:
        _run_hotspots(ctx, proj, rules, since=since, top=top)
        return

    result = compute_stats(proj.resolved_path, rules, top=top)

    summary = {
        "files": result.file_count,
        "total_lines": result.total_lines,
        "estimated_tokens": result.total_tokens,
        "total_size": human_size(result.total_size),
        "average_file_size": human_size(result.average_file_size),
    }

    if state.output.is_json:
        payload = {
            **summary,
            "languages": dict(result.language_counts),
            "largest_files": [
                {"path": f.rel_path, "size": f.size, "lines": f.lines, "tokens": f.tokens}
                for f in result.largest_files
            ],
        }
        state.output.emit_json(payload)
        cache_output("stats", proj.name, payload)
        _cache_on_project(proj.name, summary)
        return

    render_kv(state.output, f"{proj.name} — summary", summary)

    lang_rows = sorted(result.language_counts.items(), key=lambda kv: kv[1], reverse=True)
    render_table(
        state.output,
        "Languages",
        ["language", "files", "bytes"],
        [[lang, count, human_size(result.language_bytes[lang])] for lang, count in lang_rows],
    )

    render_table(
        state.output,
        f"Largest files (top {top})",
        ["path", "size", "lines", "tokens"],
        [[f.rel_path, human_size(f.size), f.lines, f.tokens] for f in result.largest_files],
    )

    cache_output(
        "stats",
        proj.name,
        {**summary, "largest_files": [{"path": f.rel_path, "size": f.size} for f in result.largest_files]},
    )
    _cache_on_project(proj.name, summary)


def _cache_on_project(project_name: str, summary: dict) -> None:
    projects = cfgmod.load_projects()
    if project_name in projects:
        projects[project_name].cached_stats = summary
        cfgmod.save_projects(projects)


def _run_hotspots(ctx: typer.Context, proj, rules, since: str, top: int) -> None:
    state = ctx.obj
    try:
        hotspots = compute_hotspots(proj.resolved_path, rules, since=since, top=top)
    except GitError as exc:
        fail(ctx, GENERAL_ERROR, str(exc))
        return

    if state.output.is_json:
        payload = {
            "since": since,
            "hotspots": [
                {
                    "path": h.rel_path,
                    "churn": h.churn,
                    "complexity": h.complexity,
                    "complexity_is_estimated": h.complexity_is_estimated,
                    "score": h.score,
                }
                for h in hotspots
            ],
        }
        state.output.emit_json(payload)
        cache_output("stats_hotspots", proj.name, payload)
        return

    if not hotspots:
        state.output.print(f"[dim]No files changed since {since!r} in '{proj.name}'.[/dim]")
    else:
        render_table(
            state.output,
            f"{proj.name} — hotspots (churn x complexity, since {since})",
            ["path", "churn", "complexity", "score"],
            [
                [h.rel_path, h.churn, f"{h.complexity}{'*' if h.complexity_is_estimated else ''}", h.score]
                for h in hotspots
            ],
        )
        if any(h.complexity_is_estimated for h in hotspots):
            state.output.info("* complexity estimated from line count (non-Python file).", level=1)

    cache_output(
        "stats_hotspots",
        proj.name,
        {"hotspots": [{"path": h.rel_path, "score": h.score} for h in hotspots]},
    )