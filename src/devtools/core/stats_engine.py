"""Repository statistics: file/line counts, language distribution, largest
files, estimated tokens. Pure computation, no I/O beyond reading files, so
it's shared cleanly between the `stats` and `doctor` commands (doctor uses
duplicate-file hashing from here too) and easy to unit test.
"""

from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from devtools.core.filesystem import file_hash, is_probably_binary
from devtools.core.ignore_rules import IgnoreRules
from devtools.core.scanner import detect_language, scan_project
from devtools.core.tokenizer import count_tokens

_PARALLEL_THRESHOLD = 64
_DEFAULT_MAX_WORKERS = 8


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


def _stat_one(entry, count_tokens_flag: bool) -> FileStat:
    lang = detect_language(entry.path)
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
    return FileStat(rel_path=entry.rel_path, language=lang, size=entry.size, lines=lines, tokens=tokens)


def compute_stats(
    root: Path,
    ignore_rules: IgnoreRules,
    top: int = 10,
    count_tokens_flag: bool = True,
    parallel: bool = True,
    max_workers: int = _DEFAULT_MAX_WORKERS,
) -> RepoStats:
    """Compute repo-wide stats.

    Reading each file's text and tokenizing it is the dominant cost here
    (more so than the directory walk itself), so — like `scan_project` — the
    per-file work is fanned out over a thread pool once there are enough
    files to make that worthwhile. Order of `all_files` doesn't matter since
    callers only ever sort/aggregate it afterward.
    """
    stats = RepoStats()
    entries = list(scan_project(root, ignore_rules, parallel=parallel, max_workers=max_workers))

    if not parallel or len(entries) < _PARALLEL_THRESHOLD:
        file_stats = [_stat_one(e, count_tokens_flag) for e in entries]
    else:
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            file_stats = list(pool.map(lambda e: _stat_one(e, count_tokens_flag), entries))

    for fs in file_stats:
        stats.file_count += 1
        stats.total_size += fs.size
        stats.language_counts[fs.language] += 1
        stats.language_bytes[fs.language] += fs.size
        stats.total_lines += fs.lines
        stats.total_tokens += fs.tokens
        stats.all_files.append(fs)

    stats.largest_files = sorted(stats.all_files, key=lambda f: f.size, reverse=True)[:top]
    return stats


def find_duplicate_files(
    root: Path,
    ignore_rules: IgnoreRules,
    parallel: bool = True,
    max_workers: int = _DEFAULT_MAX_WORKERS,
) -> dict[str, list[str]]:
    """Return {hash: [rel_paths...]} for groups of 2+ files with identical content."""
    entries = list(scan_project(root, ignore_rules, parallel=parallel, max_workers=max_workers))

    if not parallel or len(entries) < _PARALLEL_THRESHOLD:
        hashes = [(e.rel_path, file_hash(e.path)) for e in entries]
    else:
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            hashes = list(pool.map(lambda e: (e.rel_path, file_hash(e.path)), entries))

    by_hash: dict[str, list[str]] = {}
    for rel_path, h in hashes:
        if h is None:
            continue
        by_hash.setdefault(h, []).append(rel_path)
    return {h: paths for h, paths in by_hash.items() if len(paths) > 1}