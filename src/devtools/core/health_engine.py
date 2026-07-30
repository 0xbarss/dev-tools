"""`devtools health` — a single 0-100 score rolling up the project's other
signals (backlog #13, P1). Deliberately a *rollup* of existing engines
(doctor, lint, complexity, duplication) rather than a new analysis of its
own -- the goal is one number to watch trend over time (e.g. in CI, or a
weekly check-in), not a fifth opinion on what's wrong. Each category is
capped at a fixed point weight so a single catastrophic category can't
silently zero out an otherwise-healthy project's score, and each category's
summary explains *why* it lost points, so `devtools health` is a starting
point for `devtools doctor`/`lint`/`complexity`/`dupes`, not a replacement
for them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from devtools.core.complexity_engine import compute_complexity
from devtools.core.doctor_checks import run_all_checks
from devtools.core.dupes_engine import find_code_duplicates
from devtools.core.ignore_rules import IgnoreRules
from devtools.core.lint_engine import run_lint
from devtools.core.sarif_import import ExternalScanReport

# Point budget per category; must sum to 100. A second table applies when an
# external SAST report is folded in (backlog #46) so the total still sums to
# 100 rather than health scores becoming incomparable before/after adopting
# an external scanner.
_WEIGHTS = {"doctor": 25, "lint": 35, "complexity": 20, "duplication": 20}
_WEIGHTS_WITH_EXTERNAL = {"doctor": 20, "lint": 30, "complexity": 15, "duplication": 15, "external": 20}

_COMPLEXITY_THRESHOLD = 10  # matches `devtools complexity`'s own default
_DUPLICATION_MIN_LINES = 6  # matches `devtools dupes --code`'s own default


@dataclass
class HealthCategory:
    name: str
    score: int  # 0..weight
    weight: int
    summary: str


@dataclass
class HealthReport:
    categories: list[HealthCategory] = field(default_factory=list)

    @property
    def overall_score(self) -> int:
        return sum(c.score for c in self.categories)


def _doctor_category(root: Path, ignore_rules: IgnoreRules, ignored_dirs: list[str], weight: int) -> HealthCategory:
    issues = run_all_checks(root, ignore_rules, ignored_dirs)
    errors = sum(1 for i in issues if i.severity == "error")
    warnings = sum(1 for i in issues if i.severity == "warning")
    infos = sum(1 for i in issues if i.severity == "info")
    penalty = min(weight, errors * 6 + warnings * 3 + infos * 1)
    score = weight - penalty
    if not issues:
        summary = "No doctor issues found."
    else:
        summary = f"{errors} error(s), {warnings} warning(s), {infos} info issue(s) from `devtools doctor`."
    return HealthCategory("doctor", score, weight, summary)


def _lint_category(root: Path, weight: int) -> HealthCategory:
    report = run_lint(root)
    findings = report.findings
    errors = sum(1 for f in findings if f.severity == "error")
    warnings = sum(1 for f in findings if f.severity == "warning")
    ran_ecosystems = [r.linter for r in report.results if r.ran]
    penalty = min(weight, errors * 2 + warnings)
    score = weight - penalty
    if not ran_ecosystems:
        summary = "No lint adapters ran (no supported ecosystem detected, or tools not installed)."
    elif not findings:
        summary = f"No findings from {', '.join(ran_ecosystems)}."
    else:
        summary = f"{errors} error(s), {warnings} warning(s) from {', '.join(ran_ecosystems)}."
    return HealthCategory("lint", score, weight, summary)


def _complexity_category(root: Path, ignore_rules: IgnoreRules, weight: int) -> HealthCategory:
    files = compute_complexity(root, ignore_rules)
    functions = [fn for f in files for fn in f.functions]
    if not functions:
        return HealthCategory("complexity", weight, weight, "No Python functions found to analyze.")
    flagged = [fn for fn in functions if fn.complexity >= _COMPLEXITY_THRESHOLD]
    ratio = len(flagged) / len(functions)
    score = round(weight * (1 - ratio))
    summary = f"{len(flagged)}/{len(functions)} function(s) at or above complexity {_COMPLEXITY_THRESHOLD}."
    return HealthCategory("complexity", score, weight, summary)


def _duplication_category(root: Path, ignore_rules: IgnoreRules, weight: int) -> HealthCategory:
    groups = find_code_duplicates(root, ignore_rules, min_lines=_DUPLICATION_MIN_LINES)
    duplicate_lines = sum(g.lines * len(g.occurrences) for g in groups)
    if duplicate_lines == 0:
        return HealthCategory("duplication", weight, weight, "No duplicate code blocks found.")
    # Cap the penalty function rather than trying to relate duplicate_lines
    # to total repo size precisely -- 500+ duplicated lines is "bad" for
    # any repo size, so the scale flattens out instead of requiring a
    # full stats pass just to normalize a rough signal.
    penalty = min(weight, round(weight * duplicate_lines / 500))
    score = weight - penalty
    summary = f"{duplicate_lines} duplicated line(s) across {len(groups)} block(s) (`devtools dupes --code`)."
    return HealthCategory("duplication", score, weight, summary)


def _external_category(report: ExternalScanReport, weight: int) -> HealthCategory:
    penalty = min(weight, report.error_count * 4 + report.warning_count * 1)
    score = weight - penalty
    tools = ", ".join(report.tools) if report.tools else "external scanner"
    if not report.findings:
        summary = f"No findings imported from {tools}."
    else:
        summary = f"{report.error_count} error(s), {report.warning_count} warning(s) imported from {tools} ({Path(report.source_path).name})."
    return HealthCategory("external", score, weight, summary)


def compute_health(
    root: Path,
    ignore_rules: IgnoreRules,
    ignored_dirs: list[str],
    external_report: ExternalScanReport | None = None,
) -> HealthReport:
    weights = _WEIGHTS_WITH_EXTERNAL if external_report is not None else _WEIGHTS
    categories = [
        _doctor_category(root, ignore_rules, ignored_dirs, weights["doctor"]),
        _lint_category(root, weights["lint"]),
        _complexity_category(root, ignore_rules, weights["complexity"]),
        _duplication_category(root, ignore_rules, weights["duplication"]),
    ]
    if external_report is not None:
        categories.append(_external_category(external_report, weights["external"]))
    return HealthReport(categories=categories)
