"""`devtools health` — unified 0-100 health score (backlog #13). Stays
thin per the existing `commands/` convention; all real logic lives in
`core/health_engine.py`."""

from __future__ import annotations

from typing import Optional

import typer

from devtools.commands._shared import build_ignore_rules, resolve_project
from devtools.core.exit_codes import CHECK_FAILED
from devtools.core.export_engine import cache_output
from devtools.core.health_engine import compute_health
from devtools.core.output import render_table

app = typer.Typer()


def _grade(score: int) -> str:
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 60:
        return "D"
    return "F"


@app.command()
def health(
    ctx: typer.Context,
    project: Optional[str] = typer.Argument(None, help="Project to score."),
    ci: bool = typer.Option(False, "--ci", help="Exit 5 if the overall score is below --min-score."),
    min_score: int = typer.Option(70, "--min-score", help="Threshold used by --ci."),
) -> None:
    """Roll up doctor, lint, complexity, and duplication findings into a
    single 0-100 score -- a quick "is this repo trending healthy" check."""
    state = ctx.obj
    proj = resolve_project(ctx, project)
    rules = build_ignore_rules(ctx, proj)
    ignored_dirs = state.settings.ignored_dirs_for(proj.name)

    report = compute_health(proj.resolved_path, rules, ignored_dirs)
    overall = report.overall_score
    grade = _grade(overall)

    if state.output.is_json:
        payload = {
            "score": overall,
            "grade": grade,
            "categories": [
                {"name": c.name, "score": c.score, "weight": c.weight, "summary": c.summary}
                for c in report.categories
            ],
        }
        state.output.emit_json(payload)
        cache_output("health", proj.name, payload)
    else:
        color = "green" if overall >= 80 else ("yellow" if overall >= 60 else "red")
        state.output.print(f"[bold {color}]{proj.name} — health: {overall}/100 (grade {grade})[/bold {color}]")
        render_table(
            state.output,
            "Breakdown",
            ["category", "score", "of", "summary"],
            [[c.name, c.score, c.weight, c.summary] for c in report.categories],
        )
        cache_output(
            "health",
            proj.name,
            {"score": overall, "grade": grade, "categories": [{"name": c.name, "score": c.score} for c in report.categories]},
        )

    if ci and overall < min_score:
        state.exit_code = CHECK_FAILED
        raise typer.Exit(code=CHECK_FAILED)
