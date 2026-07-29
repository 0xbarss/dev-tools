"""`devtools branches` — branch analysis (backlog #17). Stays thin per the
existing `commands/` convention; all real logic lives in
`core/branches_engine.py`."""

from __future__ import annotations

from typing import Optional

import typer

from devtools.commands._shared import fail, resolve_project
from devtools.core.branches_engine import DEFAULT_STALE_DAYS, find_stale_branches, list_branch_info
from devtools.core.exit_codes import GENERAL_ERROR
from devtools.core.export_engine import cache_output
from devtools.core.output import render_table
from devtools.utils.git import GitError

app = typer.Typer()


@app.command()
def branches(
    ctx: typer.Context,
    project: Optional[str] = typer.Argument(None, help="Project to inspect."),
    stale: bool = typer.Option(False, "--stale", help="Only show branches with no commits in the last --days days."),
    days: int = typer.Option(DEFAULT_STALE_DAYS, "--days", help="Age threshold (in days) for --stale."),
) -> None:
    """List local branches with their last-commit age, author, and merged
    status -- or, with --stale, just the ones that look safe to clean up."""
    state = ctx.obj
    proj = resolve_project(ctx, project)

    try:
        infos = find_stale_branches(proj.resolved_path, days=days) if stale else list_branch_info(proj.resolved_path, days=days)
    except GitError as exc:
        fail(ctx, GENERAL_ERROR, str(exc))

    if state.output.is_json:
        payload = {
            "branches": [
                {
                    "name": b.name,
                    "last_commit_date": b.last_commit_date,
                    "last_author": b.last_author,
                    "last_subject": b.last_subject,
                    "merged": b.merged,
                    "is_current": b.is_current,
                    "age_days": b.age_days,
                }
                for b in infos
            ],
            "stale_only": stale,
            "days_threshold": days,
        }
        state.output.emit_json(payload)
        cache_output("branches", proj.name, payload)
        return

    if not infos:
        message = f"No stale branches (>= {days} days old) in '{proj.name}'." if stale else f"No branches found in '{proj.name}'."
        state.output.print(f"[green]{message}[/green]" if stale else f"[dim]{message}[/dim]")
    else:
        title = f"{proj.name} — {'stale ' if stale else ''}branches"
        render_table(
            state.output,
            title,
            ["name", "age (days)", "merged", "last author", "last subject"],
            [[b.name, b.age_days if b.age_days is not None else "?", "yes" if b.merged else "no", b.last_author, b.last_subject] for b in infos],
        )
        if stale:
            unmerged = [b for b in infos if not b.merged]
            if unmerged:
                state.output.warn(
                    f"{len(unmerged)} stale branch(es) are NOT merged -- review before deleting: "
                    + ", ".join(b.name for b in unmerged)
                )

    cache_output(
        "branches",
        proj.name,
        {"branches": [{"name": b.name, "age_days": b.age_days, "merged": b.merged} for b in infos]},
    )