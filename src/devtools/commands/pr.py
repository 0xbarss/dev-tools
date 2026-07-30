"""`devtools pr` — pull-request helpers: `describe` (backlog #19) drafts a
PR body from the diff, and `link-issues` (backlog #20) scans commit
messages since some ref for issue references, optionally as clickable
links against `issue_tracker_url`.
"""

from __future__ import annotations

from typing import List, Optional

import typer

from devtools.commands._shared import fail, resolve_project
from devtools.core.exit_codes import GENERAL_ERROR
from devtools.core.export_engine import cache_output
from devtools.core.output import render_table
from devtools.core.pr_engine import describe_pr, issue_url, link_issues, render_pr_description_markdown
from devtools.utils import git

app = typer.Typer(help="Pull-request helpers (issue linking, description drafting, and friends).")


@app.command("describe")
def describe(
    ctx: typer.Context,
    project: Optional[str] = typer.Argument(None, help="Project to describe changes for (defaults to the configured project)."),
    since: str = typer.Option("main", "--since", help="Git ref to diff against, e.g. main, a tag, or a commit sha."),
    paths: List[str] = typer.Option([], "--path", help="Limit the diff to specific path(s) (repeatable)."),
) -> None:
    """Draft a PR description from the diff since `--since`: a summary
    grouped by Conventional Commit type, the changed-file list with line
    counts, and any referenced issues -- no AI configuration required."""
    state = ctx.obj
    proj = resolve_project(ctx, project)
    root = proj.resolved_path

    if not git.is_git_repo(root):
        fail(ctx, GENERAL_ERROR, f"Project '{proj.name}' is not a git repository.")

    try:
        desc = describe_pr(root, since=since, paths=paths or None)
    except git.GitError as exc:
        fail(ctx, GENERAL_ERROR, str(exc))
        return

    tracker_url = state.settings.issue_tracker_url

    if state.output.is_json:
        payload = {
            "since": desc.since,
            "summary_bullets": desc.summary_bullets,
            "files_changed": desc.files_changed,
            "total_additions": desc.total_additions,
            "total_deletions": desc.total_deletions,
            "issue_ids": desc.issue_ids,
        }
        state.output.emit_json(payload)
        cache_output("pr-describe", proj.name, payload)
        return

    content = render_pr_description_markdown(desc, tracker_base_url=tracker_url)
    print(content)
    cache_output("pr-describe", proj.name, {"since": desc.since, "files_changed": len(desc.files_changed)})


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
