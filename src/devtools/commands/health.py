"""`devtools health` — unified 0-100 health score (backlog #13). Stays
thin per the existing `commands/` convention; all real logic lives in
`core/health_engine.py`. `--external-report` (backlog #46) folds an
imported SARIF/SAST report into the score as a fifth category.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from devtools.commands._shared import build_ignore_rules, fail, resolve_project
from devtools.core.exit_codes import CHECK_FAILED, INVALID_USAGE
from devtools.core.export_engine import cache_output
from devtools.core.health_engine import compute_health
from devtools.core.output import render_table
from devtools.core.sarif_import import ExternalReportError, load_external_report

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
    external_report: Optional[Path] = typer.Option(None, "--external-report", help="Path to a SARIF file or devtools' generic {tool, issues:[...]} JSON shape (e.g. from `devtools sonar-import`) to fold in as a fifth category."),
) -> None:
    """Roll up doctor, lint, complexity, and duplication findings (and
    optionally an imported external SAST report) into a single 0-100
    score -- a quick "is this repo trending healthy" check."""
    state = ctx.obj
    proj = resolve_project(ctx, project)
    rules = build_ignore_rules(ctx, proj)
    ignored_dirs = state.settings.ignored_dirs_for(proj.name)

    external = None
    if external_report is not None:
        try:
            external = load_external_report(external_report)
        except ExternalReportError as exc:
            fail(ctx, INVALID_USAGE, str(exc))
            return

    report = compute_health(proj.resolved_path, rules, ignored_dirs, external_report=external)
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
