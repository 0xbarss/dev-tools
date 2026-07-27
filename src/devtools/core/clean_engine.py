"""Safe cleanup target detection for `clean`.

Only ever *reports* candidates here — deletion happens in commands/clean.py
after the confirmation prompt (or --yes), keeping this module side-effect-free
and easy to test.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from devtools.core.filesystem import dir_size

# Directory/file-glob names that are always safe to treat as build/cache junk.
CLEAN_TARGET_DIR_NAMES = {
    "__pycache__", "node_modules", "build", "dist", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", ".tox", "htmlcov", ".eggs",
    ".next", ".nuxt", ".turbo", "target",  # target: common for Rust build output
}
CLEAN_TARGET_FILE_SUFFIXES = {".pyc", ".pyo"}


@dataclass
class CleanCandidate:
    path: Path
    rel_path: str
    is_dir: bool
    size: int
    mtime: datetime


def find_candidates(root: Path) -> list[CleanCandidate]:
    """Find cache/build directories and compiled-file junk under root.

    Deliberately does NOT consult ignore_rules — clean targets are exactly
    the things a .gitignore usually already hides, and cleaning is opt-in
    and confirmation-gated, so we want it to see everything.
    """
    candidates: list[CleanCandidate] = []
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            entries = list(current.iterdir())
        except OSError:
            continue
        for entry in entries:
            if entry.is_dir():
                if entry.name in CLEAN_TARGET_DIR_NAMES:
                    candidates.append(_to_candidate(entry, root, is_dir=True))
                    continue  # don't descend into a target we're about to remove wholesale
                stack.append(entry)
            elif entry.suffix in CLEAN_TARGET_FILE_SUFFIXES:
                candidates.append(_to_candidate(entry, root, is_dir=False))
    return candidates


def filter_older_than(candidates: list[CleanCandidate], cutoff: datetime) -> list[CleanCandidate]:
    return [c for c in candidates if c.mtime < cutoff]


def total_size(candidates: list[CleanCandidate]) -> int:
    return sum(c.size for c in candidates)


def _to_candidate(path: Path, root: Path, is_dir: bool) -> CleanCandidate:
    try:
        stat = path.stat()
        size = dir_size(path) if is_dir else stat.st_size
        mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
    except OSError:
        size, mtime = 0, datetime.now(timezone.utc)
    return CleanCandidate(path=path, rel_path=str(path.relative_to(root)), is_dir=is_dir, size=size, mtime=mtime)