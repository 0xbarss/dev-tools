"""Scans commit messages for issue references (`devtools pr link-issues`,
Prioritized Backlog: "Issue linking", P3).

Looks for the handful of conventions developers actually use in the wild:
GitHub/GitLab-style `#123`, Jira/Linear-style `PROJ-123`, and explicit
closing keywords (`fixes #123`, `closes JIRA-456`). It only reads commit
messages via `utils.git.log_commits` -- no network calls, no issue-tracker
API, so it works offline and needs no credentials. Turning the extracted IDs
into clickable links against a real tracker is the caller's job (the command
knows the configured tracker base URL, if any).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from devtools.utils import git

# Ordered so the more specific "TRACKER-123" pattern is tried before the
# bare "#123" pattern (a commit like "Merge PROJ-123 (see #45)" should
# surface both, not swallow one into the other).
_ISSUE_PATTERNS = [
    re.compile(r"\b([A-Z][A-Z0-9]{1,9}-\d+)\b"),  # JIRA/Linear style: PROJ-123
    re.compile(r"(?<![A-Za-z0-9_])#(\d+)\b"),  # GitHub/GitLab style: #123
]

_CLOSING_KEYWORDS = re.compile(
    r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\b", re.IGNORECASE
)


@dataclass
class IssueReference:
    issue_id: str
    commit_hash: str
    short_hash: str
    subject: str
    closes: bool = False


@dataclass
class LinkIssuesResult:
    since: str | None
    until: str
    commits_scanned: int
    references: list[IssueReference] = field(default_factory=list)

    @property
    def issue_ids(self) -> list[str]:
        """Unique issue IDs in first-seen order."""
        seen: list[str] = []
        for ref in self.references:
            if ref.issue_id not in seen:
                seen.append(ref.issue_id)
        return seen


def _extract_ids(text: str) -> list[str]:
    ids: list[str] = []
    for pattern in _ISSUE_PATTERNS:
        for m in pattern.finditer(text):
            issue_id = m.group(1)
            if issue_id not in ids:
                ids.append(issue_id)
    return ids


def link_issues(root: Path, since: str | None = None, until: str = "HEAD") -> LinkIssuesResult:
    """Scan `git log` between `since` (exclusive) and `until` for issue IDs.

    `since=None` scans the branch's full history up to `until`, which is
    rarely what you want on a real repo -- callers typically default it to
    the latest tag or the branch's merge-base with the trunk branch.
    """
    commits = git.log_commits(root, since=since, until=until)
    references: list[IssueReference] = []
    for commit in commits:
        text = f"{commit['subject']}\n{commit['body']}"
        ids = _extract_ids(text)
        if not ids:
            continue
        closes = bool(_CLOSING_KEYWORDS.search(text))
        for issue_id in ids:
            references.append(
                IssueReference(
                    issue_id=issue_id,
                    commit_hash=commit["hash"],
                    short_hash=commit["short_hash"],
                    subject=commit["subject"],
                    closes=closes,
                )
            )
    return LinkIssuesResult(since=since, until=until, commits_scanned=len(commits), references=references)


def issue_url(issue_id: str, tracker_base_url: str | None) -> str | None:
    """Best-effort link builder. GitHub/GitLab-style bare numbers need the
    repo's own issue path, so `tracker_base_url` should already point at
    e.g. `https://github.com/org/repo/issues` or `https://org.atlassian.net/browse`
    -- we just join the ID on, we don't guess the tracker from the ID shape."""
    if not tracker_base_url:
        return None
    return f"{tracker_base_url.rstrip('/')}/{issue_id}"
