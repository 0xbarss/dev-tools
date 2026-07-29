"""`devtools license-check` — best-effort local license compliance report.

Only reads license metadata that's already checked out locally
(`node_modules/*/package.json`, installed Python dist-info). Never queries a
registry — dependencies with no locally-available metadata are reported as
"unknown" rather than guessed, so this is an audit aid, not a guarantee.
"""

from __future__ import annotations

from typing import List, Optional

import typer

from devtools.commands._shared import fail, resolve_project
from devtools.core.exit_codes import CHECK_FAILED
from devtools.core.export_engine import cache_output
from devtools.core.output import render_table
from devtools.core.sbom_engine import UNKNOWN_LICENSE, build_license_report

app = typer.Typer()


@app.command("license-check")
def license_check(
    ctx: typer.Context,
    project: Optional[str] = typer.Argument(None, help="Project to check."),
    deny: List[str] = typer.Option([], "--deny", help="License names to treat as violations (repeatable, case-insensitive), e.g. --deny GPL-3.0."),
    check: bool = typer.Option(False, "--check", help="Exit 5 if any --deny'd license (or, with no --deny given, any unknown license) is found (CI use)."),
) -> None:
    """Report dependency licenses using only locally-available metadata."""
    state = ctx.obj
    proj = resolve_project(ctx, project)
    report = build_license_report(proj.resolved_path)
    denied = {d.lower() for d in deny}

    if denied:
        violations = [e for e in report.entries if e.license.lower() in denied]
        violation_reason = "denied license found"
    else:
        violations = [e for e in report.entries if e.license == UNKNOWN_LICENSE]
        violation_reason = "unknown license"

    if state.output.is_json:
        payload = {
            "dependencies": [
                {"name": e.dependency.name, "ecosystem": e.dependency.ecosystem, "license": e.license}
                for e in report.entries
            ],
            "by_license": {lic: len(entries) for lic, entries in report.by_license().items()},
            "unknown_count": report.unknown_count,
        }
        state.output.emit_json(payload)
        cache_output("license-check", proj.name, payload)
    else:
        if not report.entries:
            state.output.print(f"No dependencies found in '{proj.name}' to license-check.")
        else:
            rows = [[e.dependency.ecosystem, e.dependency.name, e.license] for e in report.entries]
            render_table(state.output, f"{proj.name} — dependency licenses", ["ecosystem", "name", "license"], rows)
            state.output.print(
                f"[dim]{report.unknown_count} of {len(report.entries)} licenses could not be determined "
                "from local metadata (no registry lookup performed).[/dim]"
            )
        cache_output(
            "license-check", proj.name,
            {"dependency_count": len(report.entries), "unknown_count": report.unknown_count},
        )

    if check and violations:
        fail(ctx, CHECK_FAILED, f"{len(violations)} dependencies failed the license check ({violation_reason}).")