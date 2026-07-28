"""`devtools review` — local PR/diff review assistant (proposal deep-dive #4)."""

from __future__ import annotations

from typing import List, Optional

import typer

from devtools.commands._shared import fail, resolve_project
from devtools.core.exit_codes import FILESYSTEM_ERROR, GENERAL_ERROR
from devtools.core.export_engine import cache_output
from devtools.core.llm_client import LLMClientError, get_client
from devtools.core.review_engine import review as review_engine, render_markdown
from devtools.utils.git import GitError

app = typer.Typer()


@app.command()
def review(
    ctx: typer.Context,
    project: Optional[str] = typer.Argument(None, help="Project to review."),
    since: str = typer.Option("main", "--since", help="Git ref to diff against, e.g. main, a tag, or a commit sha."),
    paths: List[str] = typer.Option([], "--path", help="Limit the diff to specific path(s) (repeatable)."),
) -> None:
    """Collect the diff since `--since` and produce a structured, AI-assisted
    review: bugs, style, missing tests — framed as suggestions, not blockers."""
    state = ctx.obj
    proj = resolve_project(ctx, project)

    try:
        client = get_client(state.settings)
        report = review_engine(proj.resolved_path, client, since, paths=paths or None)
    except LLMClientError as exc:
        fail(ctx, GENERAL_ERROR, str(exc))
    except GitError as exc:
        fail(ctx, FILESYSTEM_ERROR, str(exc))
    except ValueError as exc:
        fail(ctx, GENERAL_ERROR, str(exc))

    if state.output.is_json:
        payload = {
            "since": report.since,
            "summary": report.summary,
            "comments": [
                {"file": c.file, "line": c.line, "severity": c.severity, "comment": c.comment} for c in report.comments
            ],
            "raw_text": report.raw_text,
        }
        state.output.emit_json(payload)
        cache_output("review", proj.name, payload)
        return

    content = render_markdown(report, proj.name)
    print(content)
    cache_output("review", proj.name, {"since": report.since, "comment_count": len(report.comments)})
