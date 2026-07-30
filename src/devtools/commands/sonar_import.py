"""`devtools sonar-import` — import external SAST/SARIF results (backlog
#46, P3): view a report on its own, or point `devtools health
--external-report` at the same file to fold it into the overall score.
Named after the most commonly requested source (SonarQube) but works
with any SARIF exporter (CodeQL, many Semgrep configs, etc.) or the
generic `{"tool": ..., "issues": [...]}` shape.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from devtools.commands._shared import fail, resolve_project
from devtools.core.exit_codes import INVALID_USAGE
from devtools.core.export_engine import cache_output
from devtools.core.output import render_table
from devtools.core.sarif_import import ExternalReportError, load_external_report

app = typer.Typer()


@app.command("sonar-import")
def sonar_import(
    ctx: typer.Context,
    report_path: Path = typer.Argument(..., help="Path to a SARIF file, or devtools' generic {tool, issues:[...]} JSON shape."),
    project: Optional[str] = typer.Argument(None, help="Project this report is for (defaults to the configured project)."),
) -> None:
    """Parse and summarize an external SAST report. Combine with
    `devtools health --external-report <path>` to fold it into the health score."""
    state = ctx.obj
    proj = resolve_project(ctx, project)

    try:
        report = load_external_report(report_path)
    except ExternalReportError as exc:
        fail(ctx, INVALID_USAGE, str(exc))
        return

    rows = [[f.severity, f.tool, f.rule or "", f"{f.file or ''}:{f.line}" if f.file else "", f.message[:100]] for f in report.findings]

    if state.output.is_json:
        payload = {
            "source_path": report.source_path,
            "tools": report.tools,
            "error_count": report.error_count,
            "warning_count": report.warning_count,
            "findings": [
                {"tool": f.tool, "rule": f.rule, "severity": f.severity, "file": f.file, "line": f.line, "message": f.message}
                for f in report.findings
            ],
        }
        state.output.emit_json(payload)
        cache_output("sonar-import", proj.name, payload)
        return

    state.output.print(
        f"[bold]{proj.name}[/bold] — imported {len(report.findings)} finding(s) from {', '.join(report.tools) or 'external scanner'}: "
        f"{report.error_count} error(s), {report.warning_count} warning(s)."
    )
    if rows:
        render_table(state.output, "External findings", ["severity", "tool", "rule", "location", "message"], rows)
    state.output.print(f"\nRun `devtools health {proj.name} --external-report {report_path}` to fold these into the health score.")
    cache_output("sonar-import", proj.name, {"finding_count": len(report.findings), "error_count": report.error_count, "warning_count": report.warning_count})
