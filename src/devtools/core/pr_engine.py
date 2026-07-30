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


# --------------------------------------------------------------------------- #
# `devtools pr describe` (backlog #19, P1) — draft a PR body from the diff.
#
# Deliberately deterministic/template-based rather than requiring
# `llm_client.py`: composes three things the toolkit already computes
# (Conventional-Commit-classified commit log via `changelog_engine`,
# per-file diff stats, and issue references via `link_issues` above) into
# one Markdown draft. This keeps `pr describe` usable with zero AI
# configuration -- matching the project's "sane defaults, no surprises"
# philosophy -- while still being a genuinely useful starting draft.
# --------------------------------------------------------------------------- #


@dataclass
class PrDescription:
    since: str
    summary_bullets: list[str] = field(default_factory=list)
    files_changed: list[dict] = field(default_factory=list)
    issue_ids: list[str] = field(default_factory=list)
    total_additions: int = 0
    total_deletions: int = 0


def describe_pr(root: Path, since: str = "main", paths: list[str] | None = None) -> PrDescription:
    from devtools.core.changelog_engine import classify_commit

    commits = git.log_commits(root, since=since, until="HEAD")
    bullets: list[str] = []
    for commit in commits:
        section, scope, description, breaking = classify_commit(commit["subject"])
        prefix = f"**{section}:** " if section != "Other" else ""
        scope_note = f"({scope}) " if scope else ""
        marker = " **BREAKING**" if breaking else ""
        bullets.append(f"{prefix}{scope_note}{description}{marker}")

    files = git.numstat_since(root, since, paths=paths)
    total_additions = sum(f["additions"] for f in files)
    total_deletions = sum(f["deletions"] for f in files)

    issues = link_issues(root, since=since, until="HEAD")

    return PrDescription(
        since=since,
        summary_bullets=bullets,
        files_changed=files,
        issue_ids=issues.issue_ids,
        total_additions=total_additions,
        total_deletions=total_deletions,
    )


def render_pr_description_markdown(desc: PrDescription, tracker_base_url: str | None = None) -> str:
    lines = ["## Summary", ""]
    if desc.summary_bullets:
        lines.extend(f"- {b}" for b in desc.summary_bullets)
    else:
        lines.append(f"_No commits found since `{desc.since}`._")
    lines.append("")

    lines.append("## Changes")
    lines.append("")
    lines.append(f"`{len(desc.files_changed)}` file(s) changed, `+{desc.total_additions}/-{desc.total_deletions}` lines.")
    lines.append("")
    for f in desc.files_changed[:50]:
        marker = " _(binary)_" if f["binary"] else f" (+{f['additions']}/-{f['deletions']})"
        lines.append(f"- `{f['path']}`{marker}")
    if len(desc.files_changed) > 50:
        lines.append(f"- _... and {len(desc.files_changed) - 50} more file(s)_")
    lines.append("")

    if desc.issue_ids:
        lines.append("## Related issues")
        lines.append("")
        for issue_id in desc.issue_ids:
            url = issue_url(issue_id, tracker_base_url)
            lines.append(f"- {url or issue_id}")
        lines.append("")

    return "\n".join(lines)
