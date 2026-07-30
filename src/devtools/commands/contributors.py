"""`devtools contributors` — author statistics (backlog #16, P2)."""

from __future__ import annotations

from typing import Optional

import typer

from devtools.commands._shared import fail, resolve_project
from devtools.core.contributors_engine import compute_contributors
from devtools.core.exit_codes import FILESYSTEM_ERROR
from devtools.core.export_engine import cache_output
from devtools.core.output import render_table
from devtools.utils.git import GitError

app = typer.Typer()


@app.command()
def contributors(
    ctx: typer.Context,
    project: Optional[str] = typer.Argument(None, help="Project to analyze."),
    since: Optional[str] = typer.Option(None, "--since", help="A git date expression, e.g. '90 days ago', '2024-01-01', or a ref."),
    until: str = typer.Option("HEAD", "--until", help="Git ref to end at."),
    top: int = typer.Option(20, "--top", help="Limit to the N most active contributors."),
) -> None:
    """Commit and line-change counts per author, most active first."""
    state = ctx.obj
    proj = resolve_project(ctx, project)

    try:
        report = compute_contributors(proj.resolved_path, since=since, until=until)
    except GitError as exc:
        fail(ctx, FILESYSTEM_ERROR, str(exc))
        return

    contributors_list = report.contributors[:top]
    rows = [
        [c.author_name, c.commits, f"+{c.additions}/-{c.deletions}", c.first_commit_date or "", c.last_commit_date or ""]
        for c in contributors_list
    ]

    if state.output.is_json:
        payload = {
            "since": report.since,
            "until": report.until,
            "contributors": [
                {
                    "author_name": c.author_name,
                    "author_email": c.author_email,
                    "commits": c.commits,
                    "additions": c.additions,
                    "deletions": c.deletions,
                    "first_commit_date": c.first_commit_date,
                    "last_commit_date": c.last_commit_date,
                }
                for c in contributors_list
            ],
        }
        state.output.emit_json(payload)
        cache_output("contributors", proj.name, payload)
        return

    render_table(state.output, f"{proj.name} — contributors", ["author", "commits", "+/-", "first commit", "last commit"], rows)
    if not contributors_list:
        state.output.print("[dim]No commits found in range.[/dim]")
    cache_output("contributors", proj.name, {"count": len(contributors_list)})
