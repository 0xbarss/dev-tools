"""`devtools investigate` — autonomous investigation mode (Prioritized
Backlog: "Autonomous investigation mode", P2)."""

from __future__ import annotations

from typing import Optional

import typer

from devtools.commands._shared import build_ignore_rules, fail, resolve_project
from devtools.core.exit_codes import GENERAL_ERROR
from devtools.core.export_engine import cache_output
from devtools.core.investigate_engine import investigate as investigate_engine, render_markdown
from devtools.core.llm_client import LLMClientError, get_client

app = typer.Typer()


@app.command()
def investigate(
    ctx: typer.Context,
    project: Optional[str] = typer.Argument(None, help="Project to investigate within."),
    question: str = typer.Argument(..., help="The question or issue to investigate, e.g. 'why do retries sometimes double-send'."),
    max_steps: int = typer.Option(5, "--max-steps", min=1, max=15, help="Bound on search/read tool calls before forcing a conclusion."),
) -> None:
    """Autonomously search and read through the project to investigate a
    question, using a bounded search -> read -> ... -> finish loop rather
    than a single one-shot prompt (see `explain`/`context` for that)."""
    state = ctx.obj
    proj = resolve_project(ctx, project)
    rules = build_ignore_rules(ctx, proj)

    try:
        client = get_client(state.settings)
        report = investigate_engine(proj.resolved_path, rules, client, question, max_steps=max_steps)
    except LLMClientError as exc:
        fail(ctx, GENERAL_ERROR, str(exc))
    except ValueError as exc:
        fail(ctx, GENERAL_ERROR, str(exc))

    if state.output.is_json:
        payload = {
            "question": report.question,
            "summary": report.summary,
            "evidence": report.evidence,
            "steps": [{"action": s.action, "detail": s.detail} for s in report.steps],
            "raw_text": report.raw_text,
        }
        state.output.emit_json(payload)
        cache_output("investigate", proj.name, payload)
        return

    print(render_markdown(report, proj.name))
    cache_output("investigate", proj.name, {"question": report.question, "step_count": len(report.steps)})
