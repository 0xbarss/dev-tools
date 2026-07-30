"""Deterministic, pattern-based security checks for `devtools review
--security` (backlog #28, P2).

Per the proposal's own framing: "pattern rules run first and
deterministically; LLM commentary is additive and clearly separated from
the rule-based findings, avoiding false confidence." This module is the
rule-based half — it never calls an LLM and never needs one configured,
so `devtools review --security` is useful even with `ai_provider = none`.
Deliberately conservative and diff-scoped (like `review`/`collect
--since`): it only flags lines *added* by the change, not pre-existing
code the diff happens to touch, to keep signal-to-noise reasonable on a
real PR-sized diff.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from devtools.utils import git as gitutil

_DIFF_FILE_HEADER = re.compile(r"^\+\+\+ b/(.+)$")
_DIFF_HUNK_HEADER = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


@dataclass
class SecurityFinding:
    rule: str
    severity: str  # "high" | "medium" | "low"
    file: str
    line: int | None
    message: str


@dataclass
class SecurityRule:
    name: str
    pattern: re.Pattern
    severity: str
    message: str
    languages: tuple[str, ...] = ()  # empty = applies to any text file


_RULES: list[SecurityRule] = [
    SecurityRule(
        "hardcoded-secret",
        re.compile(r"(?i)\b(api[_-]?key|secret|password|token|access[_-]?key)\b\s*[:=]\s*['\"][A-Za-z0-9/+=_\-]{8,}['\"]"),
        "high",
        "Possible hardcoded credential/secret literal.",
    ),
    SecurityRule(
        "aws-access-key",
        re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
        "high",
        "String matches the shape of an AWS access key ID.",
    ),
    SecurityRule(
        "private-key-block",
        re.compile(r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----"),
        "high",
        "Embedded private key material.",
    ),
    SecurityRule(
        "python-eval-exec",
        re.compile(r"\b(eval|exec)\s*\("),
        "medium",
        "Use of eval()/exec() on potentially untrusted input.",
        languages=("python",),
    ),
    SecurityRule(
        "python-pickle-load",
        re.compile(r"\bpickle\.loads?\s*\("),
        "medium",
        "pickle.load(s) can execute arbitrary code for untrusted data.",
        languages=("python",),
    ),
    SecurityRule(
        "python-yaml-unsafe-load",
        re.compile(r"\byaml\.load\s*\((?!.*Loader\s*=\s*yaml\.SafeLoader)"),
        "medium",
        "yaml.load() without Loader=yaml.SafeLoader can execute arbitrary code.",
        languages=("python",),
    ),
    SecurityRule(
        "sql-string-format",
        re.compile(r"(?i)(execute|cursor\.execute)\s*\(\s*f?['\"].*(%s|\{.*\}|\+).*(select|insert|update|delete)\b"),
        "medium",
        "Possible SQL built via string formatting/concatenation (injection risk).",
    ),
    SecurityRule(
        "js-eval",
        re.compile(r"\beval\s*\("),
        "medium",
        "Use of eval() on potentially untrusted input.",
        languages=("javascript", "typescript"),
    ),
    SecurityRule(
        "shell-true",
        re.compile(r"shell\s*=\s*True"),
        "low",
        "subprocess call with shell=True — validate input carefully or avoid.",
        languages=("python",),
    ),
    SecurityRule(
        "disabled-tls-verify",
        re.compile(r"(?i)verify\s*=\s*False|rejectUnauthorized\s*:\s*false|NODE_TLS_REJECT_UNAUTHORIZED"),
        "high",
        "TLS/certificate verification appears to be disabled.",
    ),
]


def _language_for(path: str) -> str:
    from devtools.core.scanner import detect_language

    return detect_language(Path(path))


def _rules_for_language(language: str) -> list[SecurityRule]:
    return [r for r in _RULES if not r.languages or language in r.languages]


def scan_added_lines(file_path: str, added_lines: list[tuple[int, str]]) -> list[SecurityFinding]:
    """Scan the added lines of a single file (line_no, text) against the rule set."""
    language = _language_for(file_path)
    rules = _rules_for_language(language)
    findings: list[SecurityFinding] = []
    for line_no, text in added_lines:
        for rule in rules:
            if rule.pattern.search(text):
                findings.append(
                    SecurityFinding(rule=rule.name, severity=rule.severity, file=file_path, line=line_no, message=rule.message)
                )
    return findings


def _parse_unified_diff(diff_text: str) -> dict[str, list[tuple[int, str]]]:
    """Map file path -> list of (new_line_number, added_line_text) for every
    `+` line in a unified diff (excluding the `+++` file header itself)."""
    added_by_file: dict[str, list[tuple[int, str]]] = {}
    current_file: str | None = None
    current_line = 0
    for raw_line in diff_text.splitlines():
        file_match = _DIFF_FILE_HEADER.match(raw_line)
        if file_match:
            current_file = file_match.group(1)
            added_by_file.setdefault(current_file, [])
            continue
        hunk_match = _DIFF_HUNK_HEADER.match(raw_line)
        if hunk_match:
            current_line = int(hunk_match.group(1))
            continue
        if current_file is None:
            continue
        if raw_line.startswith("+++") or raw_line.startswith("---"):
            continue
        if raw_line.startswith("+"):
            added_by_file[current_file].append((current_line, raw_line[1:]))
            current_line += 1
        elif raw_line.startswith("-"):
            continue  # removed lines don't advance the new-file line counter
        else:
            current_line += 1
    return added_by_file


def scan_diff(root: Path, since: str, paths: list[str] | None = None) -> list[SecurityFinding]:
    """Deterministic, diff-scoped security scan: only lines the change
    *adds* are checked, so pre-existing code isn't re-flagged on every PR."""
    diff = gitutil.diff_since(root, since, paths=paths)
    added_by_file = _parse_unified_diff(diff)
    findings: list[SecurityFinding] = []
    for file_path, added_lines in added_by_file.items():
        findings.extend(scan_added_lines(file_path, added_lines))
    return findings
