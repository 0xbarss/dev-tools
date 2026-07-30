"""`devtools commit-lint` — enforce Conventional Commits over a range
(backlog #18, P2). A small, CI-shaped sibling of `changelog`/`pr
link-issues`: same read-only git-log plumbing, `--ci` exits 5 on the first
violating commit so it composes with the project's other `--ci` gates
(`doctor --ci`, `deps --check`, `lint --ci`, `health --ci`)."""

from __future__ import annotations

from typing import Optional

import typer

from devtools.commands._shared import fail, resolve_project
from devtools.core.commit_lint_engine import lint_range
from devtools.core.exit_codes import CHECK_FAILED, FILESYSTEM_ERROR, INVALID_USAGE
from devtools.core.output import render_table
from devtools.utils.git import GitError

app = typer.Typer()


@app.command("commit-lint")
def commit_lint(
    ctx: typer.Context,
    project: Optional[str] = typer.Argument(None, help="Project to scan (defaults to the configured project)."),
    since: Optional[str] = typer.Option(None, "--since", help="Git ref to scan from, exclusive (defaults to the latest tag, or full history)."),
    until: str = typer.Option("HEAD", "--until", help="Git ref to scan up to."),
    range_: Optional[str] = typer.Option(None, "--range", help="Convenience: 'A..B' sets --since A --until B in one flag."),
    ci: bool = typer.Option(False, "--ci", help="Exit 5 if any commit in range violates Conventional Commits."),
) -> None:
    """Check that every commit subject in range follows Conventional
    Commits (`type(scope): description`). Merge commits are exempt."""
    state = ctx.obj
    proj = resolve_project(ctx, project)
    root = proj.resolved_path

    effective_since, effective_until = since, until
    if range_ is not None:
        if ".." not in range_:
            fail(ctx, INVALID_USAGE, "--range must look like 'A..B', e.g. --range main..HEAD.")
        effective_since, _, effective_until = range_.partition("..")

    if effective_since is None:
        from devtools.utils import git as gitutil

        effective_since = gitutil.latest_tag(root)

    try:
        report = lint_range(root, since=effective_since, until=effective_until)
    except GitError as exc:
        fail(ctx, FILESYSTEM_ERROR, str(exc))
        return

    rows = [[v.short_hash, v.subject, "; ".join(v.reasons)] for v in report.violations]

    if state.output.is_json:
        payload = {
            "since": report.since,
            "until": report.until,
            "commits_scanned": report.commits_scanned,
            "ok": report.ok,
            "violations": [{"commit": v.short_hash, "subject": v.subject, "reasons": v.reasons} for v in report.violations],
        }
        state.output.emit_json(payload)
    else:
        state.output.info(f"Scanned {report.commits_scanned} commit(s) since {report.since or '(full history)'}.")
        if report.ok:
            state.output.print(f"[green]All commits since {report.since or '(full history)'} follow Conventional Commits.[/green]")
        else:
            render_table(state.output, "Commit-lint violations", ["commit", "subject", "reasons"], rows)

    if ci and not report.ok:
        state.exit_code = CHECK_FAILED
        raise typer.Exit(code=CHECK_FAILED)
