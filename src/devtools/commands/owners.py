"""`devtools owners` — ownership/blame analysis (backlog #15). Stays thin
per the existing `commands/` convention; all real logic lives in
`core/owners_engine.py`."""

from __future__ import annotations

from typing import Optional

import typer

from devtools.commands._shared import build_ignore_rules, fail, resolve_project
from devtools.core.exit_codes import GENERAL_ERROR
from devtools.core.export_engine import cache_output
from devtools.core.output import render_table
from devtools.core.owners_engine import compute_ownership
from devtools.utils.git import GitError

app = typer.Typer()


@app.command()
def owners(
    ctx: typer.Context,
    project: Optional[str] = typer.Argument(None, help="Project to analyze."),
    path: Optional[str] = typer.Option(None, "--path", help="Only consider files under this relative path prefix."),
    top: int = typer.Option(30, "--top", help="How many files to show, least-blamed-share first (surfaces files with no clear owner)."),
) -> None:
    """Show the top author (and their line share) per file, from `git blame`
    -- "who should review this" derived from real history, not guesswork."""
    state = ctx.obj
    proj = resolve_project(ctx, project)
    rules = build_ignore_rules(ctx, proj)

    try:
        report = compute_ownership(proj.resolved_path, rules, path_prefix=path)
    except GitError as exc:
        fail(ctx, GENERAL_ERROR, str(exc))

    rows = sorted(report.files, key=lambda f: f.top_author_share)
    shown = rows[:top]

    if state.output.is_json:
        payload = {
            "files": [
                {
                    "path": f.rel_path,
                    "total_lines": f.total_lines,
                    "top_author": f.top_author,
                    "top_author_share": f.top_author_share,
                    "authors": f.authors,
                }
                for f in report.files
            ],
            "skipped": report.skipped,
        }
        state.output.emit_json(payload)
        cache_output("owners", proj.name, payload)
        return

    if not report.files:
        state.output.print(f"[dim]No blame-able files found in '{proj.name}'.[/dim]")
    else:
        render_table(
            state.output,
            f"{proj.name} — ownership (top {len(shown)} by weakest sole ownership)",
            ["path", "top author", "share", "total lines"],
            [[f.rel_path, f.top_author, f"{f.top_author_share:.0%}", f.total_lines] for f in shown],
        )
    if report.skipped:
        state.output.info(f"{len(report.skipped)} file(s) skipped (no blame data, e.g. untracked).", level=1)

    cache_output(
        "owners",
        proj.name,
        {"files": [{"path": f.rel_path, "top_author": f.top_author, "share": f.top_author_share} for f in report.files]},
    )
