"""Repository statistics: file/line counts, language distribution, largest
files, estimated tokens. Pure computation, no I/O beyond reading files, so
it's shared cleanly between the `stats` and `doctor` commands (doctor uses
duplicate-file hashing from here too) and easy to unit test.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from devtools.core.filesystem import file_hash, is_probably_binary
from devtools.core.ignore_rules import IgnoreRules
from devtools.core.scanner import detect_language, scan_project
from devtools.core.tokenizer import count_tokens


@dataclass
class FileStat:
    rel_path: str
    language: str
    size: int
    lines: int
    tokens: int


@dataclass
class RepoStats:
    file_count: int = 0
    total_size: int = 0
    total_lines: int = 0
    total_tokens: int = 0
    language_counts: Counter = field(default_factory=Counter)
    language_bytes: Counter = field(default_factory=Counter)
    largest_files: list[FileStat] = field(default_factory=list)
    all_files: list[FileStat] = field(default_factory=list)

    @property
    def average_file_size(self) -> float:
        return self.total_size / self.file_count if self.file_count else 0.0


def compute_stats(root: Path, ignore_rules: IgnoreRules, top: int = 10, count_tokens_flag: bool = True) -> RepoStats:
    stats = RepoStats()
    for entry in scan_project(root, ignore_rules):
        lang = detect_language(entry.path)
        stats.file_count += 1
        stats.total_size += entry.size
        stats.language_counts[lang] += 1
        stats.language_bytes[lang] += entry.size

        lines = 0
        tokens = 0
        if not is_probably_binary(entry.path):
            try:
                text = entry.path.read_text(encoding="utf-8", errors="replace")
                lines = text.count("\n") + (1 if text and not text.endswith("\n") else 0)
                if count_tokens_flag:
                    tokens = count_tokens(text)
            except OSError:
                pass

        stats.total_lines += lines
        stats.total_tokens += tokens
        stats.all_files.append(
            FileStat(rel_path=entry.rel_path, language=lang, size=entry.size, lines=lines, tokens=tokens)
        )

    stats.largest_files = sorted(stats.all_files, key=lambda f: f.size, reverse=True)[:top]
    return stats


def find_duplicate_files(root: Path, ignore_rules: IgnoreRules) -> dict[str, list[str]]:
    """Return {hash: [rel_paths...]} for groups of 2+ files with identical content."""
    by_hash: dict[str, list[str]] = {}
    for entry in scan_project(root, ignore_rules):
        h = file_hash(entry.path)
        if h is None:
            continue
        by_hash.setdefault(h, []).append(entry.rel_path)
    return {h: paths for h, paths in by_hash.items() if len(paths) > 1}
