"""`devtools lint` — unified multi-language linting orchestrator (proposal
deep-dive #9 / backlog #53). Stays thin per the existing `commands/`
convention; all real logic lives in `core/lint_engine.py`."""

from __future__ import annotations

from typing import List, Optional

import typer

from devtools.commands._shared import build_ignore_rules, resolve_project
from devtools.core.exit_codes import CHECK_FAILED
from devtools.core.export_engine import cache_output
from devtools.core.ignore_rules import IgnoreRules
from devtools.core.lint_engine import run_lint
from devtools.core.output import render_table

app = typer.Typer()


@app.command()
def lint(
    ctx: typer.Context,
    project: Optional[str] = typer.Argument(None, help="Project to lint."),
    ecosystem: List[str] = typer.Option([], "--ecosystem", help="Limit to specific ecosystem(s), e.g. python, node (repeatable)."),
    fix: bool = typer.Option(False, "--fix", help="Pass through to each tool's own autofix (ruff --fix, eslint --fix, ...)."),
    ci: bool = typer.Option(False, "--ci", help="Exit 5 if any error-severity finding exists; never prompt."),
) -> None:
    """Auto-detect ecosystems present and run the right linter per language,
    merging everything into one normalized table (file, line, rule, severity,
    message, source_linter)."""
    state = ctx.obj
    proj = resolve_project(ctx, project)
    root = proj.resolved_path
    # Findings should respect the same ignore conventions as collect/grep/stats,
    # though most linters walk their own project tree; this keeps future
    # adapters (or a --paths flag) consistent with the rest of the toolkit.
    _rules: IgnoreRules = build_ignore_rules(ctx, proj)

    report = run_lint(root, fix=fix, only_ecosystems=ecosystem or None)

    skipped = [r for r in report.results if not r.ran]
    findings = report.findings
    findings_payload = [
        {
            "file": f.file,
            "line": f.line,
            "rule": f.rule,
            "severity": f.severity,
            "message": f.message,
            "source_linter": f.source_linter,
        }
        for f in findings
    ]

    if state.output.is_json:
        payload = {
            "findings": findings_payload,
            "skipped": [{"linter": r.linter, "ecosystem": r.ecosystem, "error": r.error} for r in skipped],
        }
        state.output.emit_json(payload)
        cache_output("lint", proj.name, payload)
    else:
        if not report.results:
            state.output.print(f"[dim]No known ecosystems detected in '{proj.name}'; nothing to lint.[/dim]")
        elif not findings:
            state.output.print(f"[green]No lint findings in '{proj.name}'.[/green]")
        else:
            rows = [[f.file, f.line if f.line is not None else "", f.rule or "", f.severity, f.message, f.source_linter] for f in findings]
            render_table(state.output, f"{proj.name} — lint findings", ["file", "line", "rule", "severity", "message", "source_linter"], rows)
        for r in skipped:
            state.output.warn(f"{r.error}")
        cache_output("lint", proj.name, {"findings": findings_payload})

    if ci and report.has_errors:
        state.exit_code = CHECK_FAILED
        raise typer.Exit(code=CHECK_FAILED)
