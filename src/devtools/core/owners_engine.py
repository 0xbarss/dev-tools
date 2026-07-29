"""`devtools owners` — ownership/blame analysis (backlog #15, P1).

"Who should review this file" derived from `git blame`: for each tracked,
non-binary source file, attribute lines to authors and report the top
owner (and their share of the file) plus the full author breakdown. Pure
read-only `git blame --line-porcelain` calls -- no network, matching the
project's existing philosophy.

Skipped, not failed: files git can't blame (untracked, binary, deleted
between HEAD and the working tree) are silently left out of the report
rather than raising, since "no ownership data yet" is a normal state for
a fresh or partially-committed repo, not an error.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from devtools.core.ignore_rules import IgnoreRules
from devtools.core.scanner import scan_project
from devtools.utils import git as gitmod


@dataclass
class FileOwnership:
    rel_path: str
    total_lines: int
    authors: dict[str, int] = field(default_factory=dict)  # author -> line count

    @property
    def top_author(self) -> str | None:
        if not self.authors:
            return None
        return max(self.authors, key=self.authors.get)

    @property
    def top_author_share(self) -> float:
        if not self.authors or self.total_lines == 0:
            return 0.0
        return round(self.authors[self.top_author] / self.total_lines, 4)


@dataclass
class OwnersReport:
    files: list[FileOwnership] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)  # files with no blame data

    def by_owner(self) -> dict[str, list[str]]:
        """owner -> files where they're the top author, most-owned first is
        left to the caller (commands/owners.py) to sort by whatever's useful
        for that view."""
        out: dict[str, list[str]] = {}
        for f in self.files:
            if f.top_author:
                out.setdefault(f.top_author, []).append(f.rel_path)
        return out


def compute_ownership(
    root: Path,
    ignore_rules: IgnoreRules,
    path_prefix: str | None = None,
) -> OwnersReport:
    """Blame every scanned (non-binary) file under `root`, optionally
    restricted to files whose relative path starts with `path_prefix`."""
    if not gitmod.is_git_repo(root):
        raise gitmod.GitError(f"{root} is not a git repository")

    report = OwnersReport()
    for entry in scan_project(root, ignore_rules):
        if entry.is_binary:
            continue
        if path_prefix and not entry.rel_path.startswith(path_prefix):
            continue
        counts = gitmod.blame_line_counts(root, entry.rel_path)
        if not counts:
            report.skipped.append(entry.rel_path)
            continue
        report.files.append(
            FileOwnership(rel_path=entry.rel_path, total_lines=sum(counts.values()), authors=counts)
        )
    return report