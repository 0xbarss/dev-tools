"""`devtools lint` — unified multi-language linting orchestrator.

Proposal deep-dive #9 (backlog #53). Reuses the same ecosystem-detection
philosophy `deps_engine.py` already applies to manifest parsing: read what's
there, don't reinvent the ecosystem. Each adapter below knows how to (a)
detect whether its ecosystem is present, (b) invoke its tool with a
machine-readable output format, and (c) map that tool's native JSON into one
shared `LintFinding`. A broken/missing adapter is reported clearly (with an
install hint) rather than failing the whole run.
"""

from __future__ import annotations

import json as _json
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

_TIMEOUT_SECONDS = 120


@dataclass
class LintFinding:
    file: str
    line: int | None
    rule: str | None
    severity: str  # "error" | "warning" | "info"
    message: str
    source_linter: str


@dataclass
class LintAdapterResult:
    linter: str
    ecosystem: str
    ran: bool
    findings: list[LintFinding] = field(default_factory=list)
    error: str | None = None  # e.g. "ruff not found — install with 'pip install ruff'"


@dataclass
class LintReport:
    results: list[LintAdapterResult] = field(default_factory=list)

    @property
    def findings(self) -> list[LintFinding]:
        return [f for r in self.results for f in r.findings]

    @property
    def has_errors(self) -> bool:
        return any(f.severity == "error" for f in self.findings)


def _run(cmd: list[str], cwd: Path) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=_TIMEOUT_SECONDS)
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        return -1, "", f"{cmd[0]} timed out after {_TIMEOUT_SECONDS}s"


class LintAdapter:
    name: str = ""
    ecosystem: str = ""
    tool: str = ""
    install_hint: str = ""

    def detect(self, root: Path) -> bool:
        raise NotImplementedError

    def is_available(self) -> bool:
        return shutil.which(self.tool) is not None

    def run(self, root: Path, fix: bool = False) -> LintAdapterResult:
        raise NotImplementedError


class RuffAdapter(LintAdapter):
    name = "ruff"
    ecosystem = "python"
    tool = "ruff"
    install_hint = "ruff not found — install with 'pip install ruff' or 'uv tool install ruff'"

    def detect(self, root: Path) -> bool:
        return (root / "pyproject.toml").is_file() or any(root.glob("*.py")) or (root / "requirements.txt").is_file()

    def run(self, root: Path, fix: bool = False) -> LintAdapterResult:
        if not self.is_available():
            return LintAdapterResult(self.name, self.ecosystem, ran=False, error=self.install_hint)
        cmd = ["ruff", "check", ".", "--output-format", "json"]
        if fix:
            cmd.append("--fix")
        _code, out, err = _run(cmd, root)
        findings = []
        try:
            payload = _json.loads(out) if out.strip() else []
        except _json.JSONDecodeError:
            return LintAdapterResult(self.name, self.ecosystem, ran=True, error=f"could not parse ruff output: {err[:200]}")
        for item in payload:
            findings.append(
                LintFinding(
                    file=_rel(item.get("filename", ""), root),
                    line=(item.get("location") or {}).get("row"),
                    rule=item.get("code"),
                    severity="error" if (item.get("code") or "").startswith("E") else "warning",
                    message=item.get("message", ""),
                    source_linter=self.name,
                )
            )
        return LintAdapterResult(self.name, self.ecosystem, ran=True, findings=findings)


class EslintAdapter(LintAdapter):
    name = "eslint"
    ecosystem = "node"
    tool = "eslint"
    install_hint = "eslint not found — install with 'npm install --save-dev eslint'"

    def detect(self, root: Path) -> bool:
        return (root / "package.json").is_file()

    def run(self, root: Path, fix: bool = False) -> LintAdapterResult:
        if not self.is_available():
            return LintAdapterResult(self.name, self.ecosystem, ran=False, error=self.install_hint)
        cmd = ["eslint", ".", "-f", "json"]
        if fix:
            cmd.append("--fix")
        _code, out, err = _run(cmd, root)
        try:
            payload = _json.loads(out) if out.strip() else []
        except _json.JSONDecodeError:
            return LintAdapterResult(self.name, self.ecosystem, ran=True, error=f"could not parse eslint output: {err[:200]}")
        findings = []
        for file_result in payload:
            fname = _rel(file_result.get("filePath", ""), root)
            for msg in file_result.get("messages", []):
                findings.append(
                    LintFinding(
                        file=fname,
                        line=msg.get("line"),
                        rule=msg.get("ruleId"),
                        severity="error" if msg.get("severity") == 2 else "warning",
                        message=msg.get("message", ""),
                        source_linter=self.name,
                    )
                )
        return LintAdapterResult(self.name, self.ecosystem, ran=True, findings=findings)


class ClippyAdapter(LintAdapter):
    name = "cargo-clippy"
    ecosystem = "rust"
    tool = "cargo"
    install_hint = "cargo/clippy not found — install via https://rustup.rs, then 'rustup component add clippy'"

    def detect(self, root: Path) -> bool:
        return (root / "Cargo.toml").is_file()

    def run(self, root: Path, fix: bool = False) -> LintAdapterResult:
        if not self.is_available():
            return LintAdapterResult(self.name, self.ecosystem, ran=False, error=self.install_hint)
        cmd = ["cargo", "clippy", "--message-format", "json"]
        if fix:
            cmd.extend(["--fix", "--allow-dirty"])
        _code, out, _err = _run(cmd, root)
        findings = []
        for line in out.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                item = _json.loads(line)
            except _json.JSONDecodeError:
                continue
            if item.get("reason") != "compiler-message":
                continue
            msg = item.get("message", {})
            level = msg.get("level", "warning")
            spans = msg.get("spans", [])
            primary = next((s for s in spans if s.get("is_primary")), spans[0] if spans else {})
            findings.append(
                LintFinding(
                    file=primary.get("file_name", ""),
                    line=primary.get("line_start"),
                    rule=(msg.get("code") or {}).get("code") if isinstance(msg.get("code"), dict) else msg.get("code"),
                    severity="error" if level == "error" else "warning",
                    message=msg.get("message", ""),
                    source_linter=self.name,
                )
            )
        return LintAdapterResult(self.name, self.ecosystem, ran=True, findings=findings)


class GolangciLintAdapter(LintAdapter):
    name = "golangci-lint"
    ecosystem = "go"
    tool = "golangci-lint"
    install_hint = "golangci-lint not found — install from https://golangci-lint.run/welcome/install/"

    def detect(self, root: Path) -> bool:
        return (root / "go.mod").is_file()

    def run(self, root: Path, fix: bool = False) -> LintAdapterResult:
        if not self.is_available():
            return LintAdapterResult(self.name, self.ecosystem, ran=False, error=self.install_hint)
        cmd = ["golangci-lint", "run", "--out-format", "json"]
        if fix:
            cmd.append("--fix")
        _code, out, err = _run(cmd, root)
        try:
            payload = _json.loads(out) if out.strip() else {}
        except _json.JSONDecodeError:
            return LintAdapterResult(self.name, self.ecosystem, ran=True, error=f"could not parse golangci-lint output: {err[:200]}")
        findings = []
        for item in payload.get("Issues") or []:
            pos = item.get("Pos", {})
            findings.append(
                LintFinding(
                    file=_rel(pos.get("Filename", ""), root),
                    line=pos.get("Line"),
                    rule=item.get("FromLinter"),
                    severity="warning",
                    message=item.get("Text", ""),
                    source_linter=self.name,
                )
            )
        return LintAdapterResult(self.name, self.ecosystem, ran=True, findings=findings)


class DartAnalyzeAdapter(LintAdapter):
    name = "dart-analyze"
    ecosystem = "flutter"
    tool = "dart"
    install_hint = "dart not found — install the Flutter/Dart SDK from https://dart.dev/get-dart"

    def detect(self, root: Path) -> bool:
        return (root / "pubspec.yaml").is_file()

    def run(self, root: Path, fix: bool = False) -> LintAdapterResult:
        if not self.is_available():
            return LintAdapterResult(self.name, self.ecosystem, ran=False, error=self.install_hint)
        cmd = ["dart", "analyze", "--format", "json"]
        _code, out, err = _run(cmd, root)
        try:
            payload = _json.loads(out) if out.strip() else {}
        except _json.JSONDecodeError:
            return LintAdapterResult(self.name, self.ecosystem, ran=True, error=f"could not parse dart analyze output: {err[:200]}")
        findings = []
        for item in payload.get("diagnostics") or []:
            loc = item.get("location", {})
            findings.append(
                LintFinding(
                    file=_rel((loc.get("file") or ""), root),
                    line=(loc.get("range") or {}).get("start", {}).get("line"),
                    rule=item.get("code"),
                    severity=item.get("severity", "warning").lower(),
                    message=item.get("problemMessage", ""),
                    source_linter=self.name,
                )
            )
        return LintAdapterResult(self.name, self.ecosystem, ran=True, findings=findings)


ADAPTERS: list[LintAdapter] = [
    RuffAdapter(),
    EslintAdapter(),
    ClippyAdapter(),
    GolangciLintAdapter(),
    DartAnalyzeAdapter(),
]


def _rel(path_str: str, root: Path) -> str:
    if not path_str:
        return path_str
    try:
        p = Path(path_str)
        if p.is_absolute():
            return p.relative_to(root).as_posix()
        return p.as_posix()
    except ValueError:
        return path_str


def detect_ecosystems(root: Path) -> list[LintAdapter]:
    return [a for a in ADAPTERS if a.detect(root)]


def run_lint(root: Path, fix: bool = False, only_ecosystems: list[str] | None = None) -> LintReport:
    """Run every applicable adapter and merge results into one LintReport.

    A single adapter erroring (tool missing, bad JSON) never aborts the
    others — each adapter's failure is captured on its own LintAdapterResult.
    """
    adapters = detect_ecosystems(root)
    if only_ecosystems:
        wanted = {e.lower() for e in only_ecosystems}
        adapters = [a for a in adapters if a.ecosystem in wanted]

    report = LintReport()
    for adapter in adapters:
        try:
            result = adapter.run(root, fix=fix)
        except Exception as exc:  # defensive: one broken adapter shouldn't kill the run
            result = LintAdapterResult(adapter.name, adapter.ecosystem, ran=False, error=str(exc))
        report.results.append(result)
    return report
