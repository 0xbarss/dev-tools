"""`devtools explain` — one-shot AI explanation of a file or symbol
(proposal backlog #21, P0)."""

from __future__ import annotations

from typing import Optional

import typer

from devtools.commands._shared import build_ignore_rules, fail, resolve_project
from devtools.core.exit_codes import GENERAL_ERROR
from devtools.core.explain_engine import explain as explain_engine
from devtools.core.export_engine import cache_output
from devtools.core.llm_client import LLMClientError, get_client

app = typer.Typer()


@app.command()
def explain(
    ctx: typer.Context,
    project: Optional[str] = typer.Argument(None, help="Project to explain within."),
    target: str = typer.Argument(..., help="A file path (relative to the project) or a symbol/concept name."),
) -> None:
    """Explain a file or symbol in plain language, using the same relevance
    search `context` uses to gather the right code first."""
    state = ctx.obj
    proj = resolve_project(ctx, project)
    rules = build_ignore_rules(ctx, proj)

    try:
        client = get_client(state.settings)
        explanation = explain_engine(proj.resolved_path, rules, target, client)
    except LLMClientError as exc:
        fail(ctx, GENERAL_ERROR, str(exc))
    except ValueError as exc:
        fail(ctx, GENERAL_ERROR, str(exc))

    if state.output.is_json:
        payload = {"target": target, "explanation": explanation}
        state.output.emit_json(payload)
        cache_output("explain", proj.name, payload)
        return

    state.output.print(explanation)
    cache_output("explain", proj.name, {"target": target})
