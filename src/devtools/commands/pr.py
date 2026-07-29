"""`devtools pr` — pull-request helpers.

Currently just `link-issues` (Prioritized Backlog: "Issue linking", P3):
scan commit messages since some ref for issue references and report them,
optionally as clickable links against `issue_tracker_url`.
"""

from __future__ import annotations

from typing import Optional

import typer

from devtools.commands._shared import fail, resolve_project
from devtools.core.exit_codes import GENERAL_ERROR
from devtools.core.output import render_table
from devtools.core.pr_engine import issue_url, link_issues
from devtools.utils import git

app = typer.Typer(help="Pull-request helpers (issue linking, and friends).")


@app.command("link-issues")
def link_issues_cmd(
    ctx: typer.Context,
    project: Optional[str] = typer.Argument(None, help="Project to scan (defaults to the configured project)."),
    since: Optional[str] = typer.Option(None, "--since", help="Git ref to scan from, exclusive (defaults to the latest tag, or full history if there isn't one)."),
    until: str = typer.Option("HEAD", "--until", help="Git ref to scan up to."),
) -> None:
    """Scan commit messages for issue references (#123, PROJ-123, "fixes #45", ...)."""
    state = ctx.obj
    proj = resolve_project(ctx, project)
    root = proj.resolved_path

    if not git.is_git_repo(root):
        fail(ctx, GENERAL_ERROR, f"Project '{proj.name}' is not a git repository.")

    effective_since = since if since is not None else git.latest_tag(root)

    try:
        result = link_issues(root, since=effective_since, until=until)
    except git.GitError as exc:
        fail(ctx, GENERAL_ERROR, str(exc))
        return

    tracker_url = state.settings.issue_tracker_url
    rows = [
        [ref.issue_id, ref.short_hash, ref.subject, "yes" if ref.closes else "", issue_url(ref.issue_id, tracker_url) or ""]
        for ref in result.references
    ]

    if state.output.is_json:
        state.output.emit_json(
            {
                "since": result.since,
                "until": result.until,
                "commits_scanned": result.commits_scanned,
                "issue_ids": result.issue_ids,
                "references": [
                    {
                        "issue_id": r.issue_id,
                        "commit": r.short_hash,
                        "subject": r.subject,
                        "closes": r.closes,
                        "url": issue_url(r.issue_id, tracker_url),
                    }
                    for r in result.references
                ],
            }
        )
        return

    state.output.info(f"Scanned {result.commits_scanned} commit(s) since {result.since or '(full history)'}.")
    render_table(
        state.output,
        f"Issues referenced since {result.since or '(full history)'}",
        ["issue", "commit", "subject", "closes", "url"],
        rows,
        json_key="references",
    )
    if not result.references:
        state.output.print("[dim]No issue references found.[/dim]")
