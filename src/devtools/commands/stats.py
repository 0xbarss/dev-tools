"""`devtools stats` — repository statistics (spec §6)."""

from __future__ import annotations

from typing import Optional

import typer

from devtools.commands._shared import build_ignore_rules, resolve_project
from devtools.core import config as cfgmod
from devtools.core.export_engine import cache_output
from devtools.core.output import render_kv, render_table
from devtools.core.stats_engine import compute_stats
from devtools.utils.helpers import human_size

app = typer.Typer()


@app.command()
def stats(
    ctx: typer.Context,
    project: Optional[str] = typer.Argument(None, help="Project to compute stats for."),
    top: int = typer.Option(10, "--top", help="How many largest files to show."),
) -> None:
    """Show file count, line count, language distribution, and largest files."""
    state = ctx.obj
    proj = resolve_project(ctx, project)
    rules = build_ignore_rules(ctx, proj)
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
