"""Import external SAST results (SARIF, or a simple generic JSON shape)
so tools like SonarQube/Semgrep/CodeQL can feed into `devtools health`
(backlog #46, P3) instead of living in a separate dashboard nobody checks
alongside the rest of the toolkit's signals.

Deliberately supports exactly two shapes rather than every tool's native
format: real SARIF (the emerging cross-tool standard -- CodeQL, many
Semgrep/Sonar exporters, MSVC, etc. can all emit it) and a tiny generic
JSON shape for anything that can't. No network calls, no vendor SDKs --
just reads a file the user already exported.
"""

from __future__ import annotations

import json as _json
from dataclasses import dataclass, field
from pathlib import Path

_SARIF_LEVEL_TO_SEVERITY = {"error": "error", "warning": "warning", "note": "info", "none": "info"}


class ExternalReportError(ValueError):
    pass


@dataclass
class ExternalFinding:
    tool: str
    rule: str | None
    severity: str  # normalized to "error" | "warning" | "info"
    file: str | None
    line: int | None
    message: str


@dataclass
class ExternalScanReport:
    source_path: str
    tools: list[str] = field(default_factory=list)
    findings: list[ExternalFinding] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "warning")


def _parse_sarif(data: dict, source_path: str) -> ExternalScanReport:
    tools: list[str] = []
    findings: list[ExternalFinding] = []
    for run in data.get("runs", []) or []:
        tool_name = (((run.get("tool") or {}).get("driver") or {}).get("name")) or "unknown"
        tools.append(tool_name)
        for result in run.get("results", []) or []:
            level = result.get("level", "warning")
            severity = _SARIF_LEVEL_TO_SEVERITY.get(level, "warning")
            message = ((result.get("message") or {}).get("text")) or ""
            rule = result.get("ruleId")
            file_path = None
            line = None
            locations = result.get("locations") or []
            if locations:
                phys = (locations[0].get("physicalLocation") or {})
                artifact = (phys.get("artifactLocation") or {})
                file_path = artifact.get("uri")
                region = phys.get("region") or {}
                line = region.get("startLine")
            findings.append(ExternalFinding(tool=tool_name, rule=rule, severity=severity, file=file_path, line=line, message=message))
    return ExternalScanReport(source_path=source_path, tools=sorted(set(tools)), findings=findings)


def _parse_generic(data: dict, source_path: str) -> ExternalScanReport:
    tool_name = data.get("tool", "external")
    findings = []
    for item in data.get("issues", []) or []:
        severity = str(item.get("severity", "warning")).lower()
        if severity not in ("error", "warning", "info"):
            severity = "warning"
        findings.append(
            ExternalFinding(
                tool=item.get("tool", tool_name),
                rule=item.get("rule"),
                severity=severity,
                file=item.get("file"),
                line=item.get("line"),
                message=item.get("message", ""),
            )
        )
    return ExternalScanReport(source_path=source_path, tools=sorted({f.tool for f in findings}) or [tool_name], findings=findings)


def load_external_report(path: Path) -> ExternalScanReport:
    try:
        data = _json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ExternalReportError(f"Could not read {path}: {exc}") from exc
    except _json.JSONDecodeError as exc:
        raise ExternalReportError(f"{path} is not valid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise ExternalReportError(f"{path} must contain a JSON object at the top level.")

    if "runs" in data:  # SARIF's top-level shape: {"version": "...", "runs": [...]}
        return _parse_sarif(data, str(path))
    if "issues" in data:
        return _parse_generic(data, str(path))
    raise ExternalReportError(f"{path} doesn't look like SARIF (no 'runs' key) or the generic devtools shape (no 'issues' key).")
