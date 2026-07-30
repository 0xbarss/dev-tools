"""`devtools commit` — single-commit helpers. Currently one subcommand,
`explain` (backlog #26), which explains one commit's patch in plain
English -- the one-commit-scoped sibling of `devtools review` (a range
of changes) and `devtools changelog` (many commits, grouped by type).
"""

from __future__ import annotations

from typing import Optional

import typer

from devtools.commands._shared import fail, resolve_project
from devtools.core.commit_engine import explain_commit
from devtools.core.exit_codes import FILESYSTEM_ERROR, GENERAL_ERROR
from devtools.core.export_engine import cache_output
from devtools.core.llm_client import LLMClientError, get_client
from devtools.utils.git import GitError

app = typer.Typer(help="Single-commit helpers (explain a commit in plain English).")


@app.command("explain")
def explain(
    ctx: typer.Context,
    project: Optional[str] = typer.Argument(None, help="Project to look up the commit in (defaults to the configured project)."),
    sha: str = typer.Argument(..., help="Commit sha/ref to explain, e.g. HEAD~3, or a full/short hash."),
) -> None:
    """Explain one commit's patch in plain English: what changed, likely
    why, and anything worth double-checking."""
    state = ctx.obj
    proj = resolve_project(ctx, project)

    try:
        client = get_client(state.settings)
        explanation = explain_commit(proj.resolved_path, sha, client)
    except LLMClientError as exc:
        fail(ctx, GENERAL_ERROR, str(exc))
        return
    except GitError as exc:
        fail(ctx, FILESYSTEM_ERROR, str(exc))
        return

    if state.output.is_json:
        payload = {"sha": sha, "explanation": explanation}
        state.output.emit_json(payload)
        cache_output("commit-explain", proj.name, payload)
        return

    state.output.print(explanation)
    cache_output("commit-explain", proj.name, {"sha": sha})
