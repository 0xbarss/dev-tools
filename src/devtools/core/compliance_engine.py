"""`devtools compliance report` — audit-ready compliance rollup (Prioritized
Backlog: "Compliance reporting", P2).

Deliberately doesn't reimplement any analysis: it's a thin aggregator over
checks that already exist elsewhere in the codebase — `doctor_checks.py`
(repo hygiene), `sbom_engine.py` (dependency licensing), and
`deadcode_engine.py` (unused code as a maintainability signal) — rolled up
into one score and one shareable report (Markdown or a self-contained HTML
file), the way an auditor or a team lead would want to see it, rather than
five separate command outputs to stitch together by hand.
"""

from __future__ import annotations

import html as _html
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from devtools import __version__
from devtools.core.deadcode_engine import compute_deadcode
from devtools.core.doctor_checks import run_all_checks
from devtools.core.ignore_rules import IgnoreRules
from devtools.core.sbom_engine import UNKNOWN_LICENSE, build_license_report

# Point deductions per finding, subtracted from a starting score of 100.
_SEVERITY_WEIGHT = {"error": 12, "warning": 5, "info": 1}
_DENIED_LICENSE_WEIGHT = 15
_UNKNOWN_LICENSE_WEIGHT = 2
_DEADCODE_WEIGHT = 1


@dataclass
class ComplianceFinding:
    category: str  # "hygiene" | "licensing" | "maintainability"
    severity: str  # "error" | "warning" | "info"
    message: str


@dataclass
class ComplianceReport:
    project: str
    generated_at: str
    score: int
    findings: list[ComplianceFinding] = field(default_factory=list)
    dependency_count: int = 0
    unknown_license_count: int = 0
    denied_license_count: int = 0
    deadcode_count: int = 0

    @property
    def has_errors(self) -> bool:
        return any(f.severity == "error" for f in self.findings)


def build_compliance_report(
    root: Path,
    ignore_rules: IgnoreRules,
    ignored_dirs: list[str],
    project_name: str,
    deny_licenses: list[str] | None = None,
) -> ComplianceReport:
    findings: list[ComplianceFinding] = []
    score = 100

    # --- repo hygiene (doctor's existing checks) ---------------------------
    doctor_issues = run_all_checks(root, ignore_rules, ignored_dirs)
    for issue in doctor_issues:
        findings.append(ComplianceFinding("hygiene", issue.severity, issue.message))
        score -= _SEVERITY_WEIGHT.get(issue.severity, 1)

    # --- dependency licensing (existing sbom_engine) ------------------------
    license_report = build_license_report(root)
    denied = {d.lower() for d in (deny_licenses or [])}
    denied_count = 0
    unknown_count = 0
    for entry in license_report.entries:
        lic = entry.license
        if denied and lic.lower() in denied:
            denied_count += 1
            findings.append(
                ComplianceFinding(
                    "licensing", "error", f"{entry.dependency.name} uses denied license '{lic}'."
                )
            )
            score -= _DENIED_LICENSE_WEIGHT
        elif lic == UNKNOWN_LICENSE:
            unknown_count += 1
    if unknown_count:
        findings.append(
            ComplianceFinding(
                "licensing",
                "warning",
                f"{unknown_count} of {len(license_report.entries)} dependencies have no locally-determinable license.",
            )
        )
        score -= min(unknown_count, 10) * _UNKNOWN_LICENSE_WEIGHT

    # --- maintainability (existing deadcode_engine, as a lightweight signal) -
    deadcode_count = 0
    try:
        deadcode = compute_deadcode(root, ignore_rules)
        deadcode_count = len(deadcode.unused_imports) + len(deadcode.unused_definitions)
        if deadcode_count:
            findings.append(
                ComplianceFinding(
                    "maintainability",
                    "info",
                    f"{deadcode_count} unused import(s)/definition(s) detected (advisory, not a compliance gate).",
                )
            )
            score -= min(deadcode_count, 20) * _DEADCODE_WEIGHT
    except Exception:  # pragma: no cover - deadcode is advisory, never fatal here
        pass

    score = max(0, min(100, score))

    return ComplianceReport(
        project=project_name,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        score=score,
        findings=findings,
        dependency_count=len(license_report.entries),
        unknown_license_count=unknown_count,
        denied_license_count=denied_count,
        deadcode_count=deadcode_count,
    )


def render_markdown(report: ComplianceReport) -> str:
    lines = [
        f"# Compliance report — {report.project}",
        "",
        f"_Generated {report.generated_at} by devtools {__version__}_",
        "",
        f"**Score: {report.score}/100**",
        "",
        f"- Dependencies scanned: {report.dependency_count}",
        f"- Unknown licenses: {report.unknown_license_count}",
        f"- Denied licenses: {report.denied_license_count}",
        f"- Dead code findings: {report.deadcode_count}",
        "",
    ]
    if not report.findings:
        lines.append("No findings — clean bill of health.")
        return "\n".join(lines)

    lines.append("## Findings")
    lines.append("")
    for category in ("hygiene", "licensing", "maintainability"):
        cat_findings = [f for f in report.findings if f.category == category]
        if not cat_findings:
            continue
        lines.append(f"### {category.capitalize()}")
        lines.append("")
        for f in cat_findings:
            lines.append(f"- **[{f.severity}]** {f.message}")
        lines.append("")
    return "\n".join(lines)


_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Compliance report — {project}</title>
<style>
  body {{ font-family: -apple-system, Segoe UI, Helvetica, Arial, sans-serif; margin: 2rem auto; max-width: 860px; color: #1a1a1a; }}
  h1 {{ margin-bottom: 0.25rem; }}
  .meta {{ color: #666; font-size: 0.9rem; margin-bottom: 1.5rem; }}
  .score {{ font-size: 2.5rem; font-weight: 700; }}
  .score.good {{ color: #1a7f37; }}
  .score.warn {{ color: #9a6700; }}
  .score.bad {{ color: #c0271d; }}
  table {{ border-collapse: collapse; width: 100%; margin: 0.5rem 0 1.5rem; }}
  td, th {{ border: 1px solid #ddd; padding: 0.4rem 0.6rem; text-align: left; font-size: 0.9rem; }}
  th {{ background: #f5f5f5; }}
  .sev-error {{ color: #c0271d; font-weight: 600; }}
  .sev-warning {{ color: #9a6700; font-weight: 600; }}
  .sev-info {{ color: #555; }}
  section {{ margin-bottom: 1.5rem; }}
</style>
</head>
<body>
<h1>Compliance report — {project}</h1>
<div class="meta">Generated {generated_at} by devtools {version}</div>
<div class="score {score_class}">{score}/100</div>
<section>
<table>
<tr><th>Dependencies scanned</th><td>{dependency_count}</td></tr>
<tr><th>Unknown licenses</th><td>{unknown_license_count}</td></tr>
<tr><th>Denied licenses</th><td>{denied_license_count}</td></tr>
<tr><th>Dead code findings</th><td>{deadcode_count}</td></tr>
</table>
</section>
{findings_html}
</body>
</html>
"""


def render_html(report: ComplianceReport) -> str:
    score_class = "good" if report.score >= 85 else ("warn" if report.score >= 60 else "bad")

    if not report.findings:
        findings_html = "<section><p>No findings — clean bill of health.</p></section>"
    else:
        blocks = []
        for category in ("hygiene", "licensing", "maintainability"):
            cat_findings = [f for f in report.findings if f.category == category]
            if not cat_findings:
                continue
            rows = "\n".join(
                f'<tr><td class="sev-{f.severity}">{_html.escape(f.severity)}</td>'
                f"<td>{_html.escape(f.message)}</td></tr>"
                for f in cat_findings
            )
            blocks.append(
                f"<section><h2>{category.capitalize()}</h2><table>"
                f"<tr><th>Severity</th><th>Message</th></tr>{rows}</table></section>"
            )
        findings_html = "\n".join(blocks)

    return _HTML_TEMPLATE.format(
        project=_html.escape(report.project),
        generated_at=report.generated_at,
        version=__version__,
        score=report.score,
        score_class=score_class,
        dependency_count=report.dependency_count,
        unknown_license_count=report.unknown_license_count,
        denied_license_count=report.denied_license_count,
        deadcode_count=report.deadcode_count,
        findings_html=findings_html,
    )
