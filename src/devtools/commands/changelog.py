"""`devtools changelog` — Keep-a-Changelog-style release notes from git history
(proposal deep-dive #3)."""

from __future__ import annotations

from typing import Optional

import typer

from devtools.commands._shared import fail, resolve_project
from devtools.core.changelog_engine import generate_changelog, render_markdown
from devtools.core.exit_codes import FILESYSTEM_ERROR
from devtools.core.export_engine import cache_output
from devtools.utils.git import GitError

app = typer.Typer()


@app.command()
def changelog(
    ctx: typer.Context,
    project: Optional[str] = typer.Argument(None, help="Project to generate a changelog for."),
    since: Optional[str] = typer.Option(None, "--since", help="Git ref to start from (tag, sha, branch). Defaults to full history."),
    until: str = typer.Option("HEAD", "--until", help="Git ref to end at."),
) -> None:
    """Group commits since `--since` by Conventional Commit type into a
    Keep-a-Changelog-style Markdown document."""
    state = ctx.obj
    proj = resolve_project(ctx, project)

    try:
        report = generate_changelog(proj.resolved_path, since=since, until=until)
    except GitError as exc:
        fail(ctx, FILESYSTEM_ERROR, str(exc))

    if state.output.is_json:
        payload = {
            "since": report.since,
            "until": report.until,
            "entries": [
                {
                    "section": e.section,
                    "scope": e.scope,
                    "description": e.description,
                    "short_hash": e.short_hash,
                    "author_name": e.author_name,
                    "breaking": e.breaking,
                }
                for e in report.entries + report.unclassified
            ],
        }
        state.output.emit_json(payload)
        cache_output("changelog", proj.name, payload)
        return

    content = render_markdown(report, title=f"{proj.name} — Changelog")
    print(content)
    cache_output("changelog", proj.name, {"entry_count": len(report.entries) + len(report.unclassified)})
