"""`devtools changelog` / `devtools release-notes` (proposal deep-dive #3).

`utils/git.py` already exists but git-history features were entirely
missing — this is the "small effort, big daily value" gap the proposal
calls out. Groups commits by Conventional Commit type into a
Keep-a-Changelog-style Markdown document. The classifier is regex-based
today; an LLM-assisted classifier for non-conventional commit messages can
be layered on later without changing this module's public shape.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from devtools.utils import git as gitutil

# Conventional Commit types -> a stable, human-friendly Keep-a-Changelog
# section heading and sort order.
_TYPE_SECTIONS: list[tuple[str, str]] = [
    ("feat", "Added"),
    ("fix", "Fixed"),
    ("perf", "Performance"),
    ("refactor", "Changed"),
    ("docs", "Documentation"),
    ("test", "Tests"),
    ("build", "Build"),
    ("ci", "CI"),
    ("style", "Style"),
    ("revert", "Reverted"),
    ("chore", "Chores"),
]
_SECTION_BY_TYPE = dict(_TYPE_SECTIONS)
_SECTION_ORDER = [section for _type, section in _TYPE_SECTIONS] + ["Other"]

_CONVENTIONAL_RE = re.compile(
    r"^(?P<type>[a-zA-Z]+)(?:\((?P<scope>[^)]*)\))?(?P<breaking>!)?:\s*(?P<description>.+)$"
)


@dataclass
class ChangelogEntry:
    section: str
    scope: str | None
    description: str
    short_hash: str
    author_name: str
    breaking: bool = False


@dataclass
class ChangelogReport:
    since: str | None
    until: str
    entries: list[ChangelogEntry] = field(default_factory=list)
    unclassified: list[ChangelogEntry] = field(default_factory=list)

    def by_section(self) -> dict[str, list[ChangelogEntry]]:
        grouped: dict[str, list[ChangelogEntry]] = {}
        for entry in self.entries + self.unclassified:
            grouped.setdefault(entry.section, []).append(entry)
        return grouped


def classify_commit(subject: str) -> tuple[str, str | None, str, bool]:
    """Return (section, scope, description, breaking) for one commit subject."""
    match = _CONVENTIONAL_RE.match(subject.strip())
    if not match:
        return "Other", None, subject.strip(), False
    commit_type = match.group("type").lower()
    scope = match.group("scope")
    breaking = bool(match.group("breaking"))
    description = match.group("description").strip()
    section = _SECTION_BY_TYPE.get(commit_type, "Other")
    return section, scope, description, breaking


def generate_changelog(root: Path, since: str | None = None, until: str = "HEAD") -> ChangelogReport:
    commits = gitutil.log_commits(root, since=since, until=until)
    report = ChangelogReport(since=since, until=until)
    for commit in commits:
        section, scope, description, breaking = classify_commit(commit["subject"])
        entry = ChangelogEntry(
            section=section,
            scope=scope,
            description=description,
            short_hash=commit["short_hash"],
            author_name=commit["author_name"],
            breaking=breaking,
        )
        if section == "Other":
            report.unclassified.append(entry)
        else:
            report.entries.append(entry)
    return report


def render_markdown(report: ChangelogReport, title: str | None = None) -> str:
    range_label = f"{report.since}..{report.until}" if report.since else report.until
    lines = [f"# {title or 'Changelog'}", "", f"_Range: `{range_label}`_", ""]
    grouped = report.by_section()
    any_section = False
    for section in _SECTION_ORDER:
        entries = grouped.get(section)
        if not entries:
            continue
        any_section = True
        lines.append(f"## {section}")
        lines.append("")
        for e in entries:
            scope_prefix = f"**{e.scope}:** " if e.scope else ""
            breaking_marker = " **BREAKING**" if e.breaking else ""
            lines.append(f"- {scope_prefix}{e.description}{breaking_marker} ({e.short_hash} by {e.author_name})")
        lines.append("")
    if not any_section:
        lines.append("_No commits in range._")
        lines.append("")
    return "\n".join(lines)