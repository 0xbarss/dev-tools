"""`devtools compliance report` — audit-ready HTML/Markdown rollup
(Prioritized Backlog: "Compliance reporting", P2)."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import typer

from devtools.commands._shared import build_ignore_rules, fail, resolve_project
from devtools.core.compliance_engine import build_compliance_report, render_html, render_markdown
from devtools.core.exit_codes import CHECK_FAILED, INVALID_USAGE
from devtools.core.export_engine import cache_output
from devtools.core.notify_engine import load_targets, send_notification
from devtools.core.output import render_kv

app = typer.Typer(help="Audit-ready compliance rollups combining doctor, licensing, and dead-code signals.")


@app.command("report")
def report(
    ctx: typer.Context,
    project: Optional[str] = typer.Argument(None, help="Project to audit."),
    deny: List[str] = typer.Option([], "--deny", help="License names to treat as violations (repeatable)."),
    html_out: Optional[Path] = typer.Option(None, "--html", help="Write a self-contained HTML report to this path."),
    check: bool = typer.Option(False, "--check", help="Exit 5 if any error-severity finding exists (CI use)."),
    notify: Optional[str] = typer.Option(None, "--notify", help="Send a summary to this configured `devtools notify` target."),
) -> None:
    """Produce a single audit-ready compliance report: repo hygiene (doctor),
    dependency licensing (sbom/license-check), and dead-code as a
    maintainability signal — with one overall 0-100 score."""
    state = ctx.obj
    proj = resolve_project(ctx, project)
    rules = build_ignore_rules(ctx, proj)
    ignored_dirs = state.settings.ignored_dirs_for(proj.name)

    compliance = build_compliance_report(
        proj.resolved_path, rules, ignored_dirs, proj.name, deny_licenses=deny or None
    )

    if html_out is not None:
        html_out.parent.mkdir(parents=True, exist_ok=True)
        html_out.write_text(render_html(compliance), encoding="utf-8")

    if notify is not None:
        targets = load_targets()
        target = targets.get(notify)
        if target is None:
            fail(ctx, INVALID_USAGE, f"No notification target named '{notify}'. Run `devtools notify list`.")
        summary = f"Compliance score {compliance.score}/100 for '{proj.name}' ({len(compliance.findings)} finding(s))."
        send_notification(
            target,
            event="devtools compliance report",
            message=summary,
            fields={"project": proj.name, "score": compliance.score, "errors": sum(1 for f in compliance.findings if f.severity == "error")},
        )

    payload = {
        "project": compliance.project,
        "generated_at": compliance.generated_at,
        "score": compliance.score,
        "dependency_count": compliance.dependency_count,
        "unknown_license_count": compliance.unknown_license_count,
        "denied_license_count": compliance.denied_license_count,
        "deadcode_count": compliance.deadcode_count,
        "findings": [{"category": f.category, "severity": f.severity, "message": f.message} for f in compliance.findings],
    }

    if state.output.is_json:
        state.output.emit_json(payload)
    else:
        render_kv(
            state.output,
            f"{proj.name} — compliance report",
            {
                "score": f"{compliance.score}/100",
                "dependencies": compliance.dependency_count,
                "unknown_licenses": compliance.unknown_license_count,
                "denied_licenses": compliance.denied_license_count,
                "deadcode_findings": compliance.deadcode_count,
                "total_findings": len(compliance.findings),
            },
        )
        if compliance.findings:
            print()
            print(render_markdown(compliance))
        if html_out is not None:
            state.output.print(f"[green]Wrote HTML report to {html_out}[/green]")

    cache_output("compliance", proj.name, payload)

    if check and compliance.has_errors:
        state.exit_code = CHECK_FAILED
        raise typer.Exit(code=CHECK_FAILED)