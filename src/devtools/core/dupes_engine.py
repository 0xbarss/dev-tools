"""Near-duplicate code block detection (proposal #12): `devtools dupes
--code`. Exact whole-file duplicates already have a home in
`stats_engine.find_duplicate_files` (used by `doctor`); this module adds
finer-grained, code-level detection via token-shingling — fixed-size
windows of consecutive non-blank, whitespace-normalized lines, hashed and
compared across the whole project, independent of file boundaries or exact
indentation/formatting.

Windows are taken at a fixed `min_lines` *stride* (non-overlapping) rather
than sliding one line at a time. A sliding-by-1 approach finds every
possible overlap but then reports one duplicate group per shifted window of
the same underlying block — a single real 20-line duplicate would explode
into over a dozen overlapping "findings". Striding by `min_lines` trades a
little recall (a duplicate that straddles two windows without being a clean
multiple of `min_lines` may be missed or reported as two adjacent blocks)
for a report that's stable, fast, and not dominated by cascade noise —
consistent with the pragmatic, "good enough signal" philosophy already used
by `is_probably_binary`'s heuristic and `find_duplicate_files`'s exact hash
comparison.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

from devtools.core.filesystem import read_text_safely
from devtools.core.ignore_rules import IgnoreRules
from devtools.core.scanner import scan_project

_WS_RE = re.compile(r"\s+")


@dataclass
class DuplicateBlock:
    rel_path: str
    start_line: int
    end_line: int


@dataclass
class DuplicateGroup:
    signature: str
    lines: int
    occurrences: list[DuplicateBlock] = field(default_factory=list)


def _normalize_line(line: str) -> str:
    return _WS_RE.sub(" ", line.strip())


def _windows(lines: list[str], size: int) -> list[tuple[int, int, str]]:
    """Return (start_line, end_line, joined_normalized_text) for
    non-overlapping windows of `size` consecutive non-blank lines.

    Blank lines are dropped before windowing (not just normalized) so two
    blocks that differ only in blank-line spacing still shingle identically.
    Line numbers in the result refer to the original file.
    """
    numbered = [(i + 1, _normalize_line(line)) for i, line in enumerate(lines)]
    numbered = [(n, t) for n, t in numbered if t]

    windows: list[tuple[int, int, str]] = []
    i = 0
    while i + size <= len(numbered):
        window = numbered[i : i + size]
        start = window[0][0]
        end = window[-1][0]
        text = "\n".join(t for _, t in window)
        windows.append((start, end, text))
        i += size
    return windows


def find_code_duplicates(
    root: Path,
    ignore_rules: IgnoreRules,
    min_lines: int = 6,
    languages: list[str] | None = None,
) -> list[DuplicateGroup]:
    """Find near-duplicate code blocks of at least `min_lines` consecutive
    non-blank lines, via exact-match token shingling (whitespace-normalized).

    Catches copy-pasted blocks even across files or with reformatted
    indentation, but — unlike a real clone detector — won't catch renamed
    identifiers or reordered statements (that's a type-2/3 clone problem;
    this is intentionally type-1/near-type-1 only). Good enough as a "these
    look suspiciously alike, go take a look" signal, same spirit as
    `find_duplicate_files`'s exact-hash file comparison.
    """
    by_hash: dict[str, DuplicateGroup] = {}

    for entry in scan_project(root, ignore_rules, languages=languages):
        text = read_text_safely(entry.path)
        if text is None:
            continue
        lines = text.splitlines()
        for start, end, normalized in _windows(lines, min_lines):
            h = hashlib.sha1(normalized.encode("utf-8")).hexdigest()
            group = by_hash.setdefault(h, DuplicateGroup(signature=h, lines=min_lines))
            group.occurrences.append(DuplicateBlock(rel_path=entry.rel_path, start_line=start, end_line=end))

    groups = [g for g in by_hash.values() if len(g.occurrences) > 1]
    groups.sort(key=lambda g: len(g.occurrences), reverse=True)
    return groups
