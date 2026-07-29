"""Fast project-aware search, shared by `grep`, `context`, and `search`."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from devtools.core.ignore_rules import IgnoreRules
from devtools.core.scanner import scan_project


@dataclass
class GrepMatch:
    rel_path: str
    line_number: int
    line: str
    context_before: list[str]
    context_after: list[str]


def grep(
    root: Path,
    ignore_rules: IgnoreRules,
    query: str,
    regex: bool = False,
    languages: list[str] | None = None,
    context: int = 0,
    case_sensitive: bool = True,
) -> list[GrepMatch]:
    flags = 0 if case_sensitive else re.IGNORECASE
    if regex:
        pattern = re.compile(query, flags)
    else:
        pattern = re.compile(re.escape(query), flags)

    matches: list[GrepMatch] = []
    for entry in scan_project(root, ignore_rules, languages=languages):
        if entry.is_binary:
            continue
        try:
            text = entry.path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if pattern.search(line):
                before = lines[max(0, i - context):i] if context else []
                after = lines[i + 1:i + 1 + context] if context else []
                matches.append(
                    GrepMatch(
                        rel_path=entry.rel_path,
                        line_number=i + 1,
                        line=line,
                        context_before=before,
                        context_after=after,
                    )
                )
    return matches