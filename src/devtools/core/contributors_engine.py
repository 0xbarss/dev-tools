"""`devtools contributors` — commit/line counts per author over a range
(backlog #16, P2). Sits next to `owners_engine.py` (which answers "who
owns this *file*") by answering "who has been active in this *repo*",
using the same `utils/git.py` plumbing rather than a new git wrapper.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from devtools.utils import git as gitutil


@dataclass
class ContributorStats:
    author_name: str
    author_email: str
    commits: int = 0
    additions: int = 0
    deletions: int = 0
    first_commit_date: str | None = None
    last_commit_date: str | None = None

    @property
    def lines_changed(self) -> int:
        return self.additions + self.deletions


@dataclass
class ContributorsReport:
    since: str | None
    until: str
    contributors: list[ContributorStats] = field(default_factory=list)


def compute_contributors(root: Path, since: str | None = None, until: str = "HEAD") -> ContributorsReport:
    commits = gitutil.author_numstat(root, since=since, until=until)
    by_email: dict[str, ContributorStats] = {}
    for c in commits:
        key = c["author_email"] or c["author_name"]
        stats = by_email.get(key)
        if stats is None:
            stats = ContributorStats(author_name=c["author_name"], author_email=c["author_email"])
            by_email[key] = stats
        stats.commits += 1
        stats.additions += c["additions"]
        stats.deletions += c["deletions"]
        date = c["date"]
        if stats.first_commit_date is None or date < stats.first_commit_date:
            stats.first_commit_date = date
        if stats.last_commit_date is None or date > stats.last_commit_date:
            stats.last_commit_date = date

    ordered = sorted(by_email.values(), key=lambda s: s.commits, reverse=True)
    return ContributorsReport(since=since, until=until, contributors=ordered)
