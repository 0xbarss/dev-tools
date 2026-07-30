"""`devtools commit-lint` — Conventional Commit enforcement (backlog #18, P2).

Deliberately reuses `changelog_engine.CONVENTIONAL_TYPES` rather than
maintaining a second list of commit types, so a type recognized by
`changelog` is automatically recognized by `commit-lint` and vice versa.
Read-only: this only inspects `git log` output, the same as `pr
link-issues` and `changelog` -- no commit-msg hook is installed unless the
caller explicitly asks (see `commands/commit_lint.py`'s `--install-hook`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from devtools.core.changelog_engine import CONVENTIONAL_TYPES
from devtools.utils import git as gitutil

_MAX_SUBJECT_LENGTH = 100

_CONVENTIONAL_RE = re.compile(
    r"^(?P<type>[a-z]+)(?:\((?P<scope>[^)]*)\))?(?P<breaking>!)?:\s(?P<description>.+)$"
)

_MERGE_RE = re.compile(r"^Merge (branch|pull request|remote-tracking branch)\b")


@dataclass
class CommitLintViolation:
    short_hash: str
    subject: str
    reasons: list[str]


@dataclass
class CommitLintReport:
    since: str | None
    until: str
    commits_scanned: int
    violations: list[CommitLintViolation] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations


def lint_subject(subject: str) -> list[str]:
    """Return a list of human-readable violation reasons for one commit
    subject, or an empty list if it's a valid Conventional Commit."""
    subject = subject.strip()
    if not subject:
        return ["empty commit subject"]
    if _MERGE_RE.match(subject):
        return []  # merge commits are exempt -- they're not authored freely

    reasons: list[str] = []
    match = _CONVENTIONAL_RE.match(subject)
    if not match:
        reasons.append(
            "does not match '<type>(<scope>)?: <description>' "
            f"(known types: {', '.join(CONVENTIONAL_TYPES)})"
        )
        return reasons

    commit_type = match.group("type")
    description = match.group("description")
    if commit_type not in CONVENTIONAL_TYPES:
        reasons.append(f"unknown type '{commit_type}' (known types: {', '.join(CONVENTIONAL_TYPES)})")
    if description[:1].isupper():
        reasons.append("description should start lowercase (Conventional Commits convention)")
    if description.endswith("."):
        reasons.append("description should not end with a period")
    if len(subject) > _MAX_SUBJECT_LENGTH:
        reasons.append(f"subject is {len(subject)} chars, longer than {_MAX_SUBJECT_LENGTH}")
    return reasons


def lint_range(root: Path, since: str | None = None, until: str = "HEAD") -> CommitLintReport:
    commits = gitutil.log_commits(root, since=since, until=until)
    violations: list[CommitLintViolation] = []
    for commit in commits:
        reasons = lint_subject(commit["subject"])
        if reasons:
            violations.append(CommitLintViolation(short_hash=commit["short_hash"], subject=commit["subject"], reasons=reasons))
    return CommitLintReport(since=since, until=until, commits_scanned=len(commits), violations=violations)
