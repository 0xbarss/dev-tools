"""`devtools review` — local PR/diff review assistant (proposal deep-dive #4).

`--security` (backlog #28) layers a deterministic, pattern-based scan
(`core/security_engine.py`) *underneath* the existing AI review: pattern
findings always show up, even with no AI provider configured, and the AI
commentary — when available — is clearly separated and told not to
re-report what the deterministic pass already caught.
"""

from __future__ import annotations

from typing import List, Optional

import typer

from devtools.commands._shared import fail, resolve_project
from devtools.core.exit_codes import FILESYSTEM_ERROR, GENERAL_ERROR
from devtools.core.export_engine import cache_output
from devtools.core.llm_client import LLMClientError, NoneClient, get_client
from devtools.core.review_engine import review as review_engine, render_markdown
from devtools.core.security_engine import scan_diff
from devtools.utils import git as gitutil
from devtools.utils.git import GitError

app = typer.Typer()


@app.command()
def review(
    ctx: typer.Context,
    project: Optional[str] = typer.Argument(None, help="Project to review."),
    since: str = typer.Option("main", "--since", help="Git ref to diff against, e.g. main, a tag, or a commit sha."),
    paths: List[str] = typer.Option([], "--path", help="Limit the diff to specific path(s) (repeatable)."),
    security: bool = typer.Option(False, "--security", help="Add a deterministic, pattern-based security scan (secrets, eval/pickle, TLS, ...) alongside the review."),
) -> None:
    """Collect the diff since `--since` and produce a structured, AI-assisted
    review: bugs, style, missing tests — framed as suggestions, not blockers."""
    state = ctx.obj
    proj = resolve_project(ctx, project)

    try:
        diff_text = gitutil.diff_since(proj.resolved_path, since, paths=paths or None)
    except GitError as exc:
        fail(ctx, FILESYSTEM_ERROR, str(exc))
        return
    if not diff_text.strip():
        fail(ctx, GENERAL_ERROR, f"No changes since '{since}' — nothing to review.")
        return

    security_findings = scan_diff(proj.resolved_path, since, paths=paths or None) if security else []

    client = get_client(state.settings)
    report = None
    ai_error: str | None = None
    if isinstance(client, NoneClient):
        if not security:
            fail(
                ctx,
                GENERAL_ERROR,
                "No AI provider configured. Run `devtools config set ai_provider claude|openai|ollama` "
                "(and set the matching API key env var, or start Ollama locally) to enable AI-assisted commands. "
                "Or pass --security for a pattern-based scan that doesn't need one.",
            )
            return
        ai_error = "No AI provider configured — showing pattern-based findings only. Run `devtools config set ai_provider claude|openai|ollama` for AI commentary too."
    else:
        try:
            report = review_engine(proj.resolved_path, client, since, paths=paths or None, security=security)
        except LLMClientError as exc:
            if not security:
                fail(ctx, GENERAL_ERROR, str(exc))
                return
            ai_error = str(exc)
        except ValueError as exc:
            if not security:
                fail(ctx, GENERAL_ERROR, str(exc))
                return
            ai_error = str(exc)

    if state.output.is_json:
        payload = {
            "since": since,
            "security_findings": [
                {"rule": f.rule, "severity": f.severity, "file": f.file, "line": f.line, "message": f.message}
                for f in security_findings
            ],
            "ai_review": None,
            "ai_error": ai_error,
        }
        if report is not None:
            payload["ai_review"] = {
                "summary": report.summary,
                "comments": [
                    {"file": c.file, "line": c.line, "severity": c.severity, "comment": c.comment} for c in report.comments
                ],
                "raw_text": report.raw_text,
            }
        state.output.emit_json(payload)
        cache_output("review", proj.name, payload)
        return

    if security:
        if security_findings:
            print(f"## Security scan (pattern-based, advisory) — {len(security_findings)} finding(s)\n")
            for f in security_findings:
                loc = f"{f.file}:{f.line}" if f.line else f.file
                print(f"- **[{f.severity}/{f.rule}]** `{loc}` — {f.message}")
            print()
        else:
            print("## Security scan (pattern-based, advisory) — no findings\n")

    if report is not None:
        content = render_markdown(report, proj.name)
        print(content)
    elif ai_error:
        state.output.warn(ai_error)

    cache_output(
        "review",
        proj.name,
        {"since": since, "security_finding_count": len(security_findings), "comment_count": len(report.comments) if report else 0},
    )
