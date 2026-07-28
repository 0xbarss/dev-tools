"""Thin subprocess wrapper around git, used by `collect --since` and `doctor`.

No GitPython dependency — git itself is assumed to be on PATH (a reasonable
assumption for a developer toolkit), and we only ever shell out to read-only
plumbing commands.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


class GitError(RuntimeError):
    pass


def _run(root: Path, args: list[str]) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except FileNotFoundError as exc:
        raise GitError("git is not installed or not on PATH") from exc
    if result.returncode != 0:
        raise GitError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout


def is_git_repo(root: Path) -> bool:
    return (root / ".git").exists()


def changed_files_since(root: Path, ref: str) -> list[Path]:
    """Files changed (added/modified/renamed target) since `ref`, relative to root."""
    if not is_git_repo(root):
        raise GitError(f"{root} is not a git repository")
    out = _run(root, ["diff", "--name-only", "--diff-filter=ACMR", ref, "--"])
    return [root / line.strip() for line in out.splitlines() if line.strip()]


def current_branch(root: Path) -> str | None:
    if not is_git_repo(root):
        return None
    try:
        out = _run(root, ["rev-parse", "--abbrev-ref", "HEAD"])
        return out.strip() or None
    except GitError:
        return None


_LOG_SEP = "\x1f"  # unit separator: unlikely to appear in a commit message
_LOG_FORMAT = _LOG_SEP.join(["%H", "%h", "%an", "%ae", "%aI", "%s", "%b"]) + "\x1e"  # \x1e = record sep


def log_commits(root: Path, since: str | None = None, until: str = "HEAD") -> list[dict]:
    """Structured `git log` entries between `since` (exclusive) and `until`.

    Each entry: hash, short_hash, author_name, author_email, date (ISO 8601),
    subject, body. `since=None` returns the full history up to `until`.
    """
    if not is_git_repo(root):
        raise GitError(f"{root} is not a git repository")
    range_arg = f"{since}..{until}" if since else until
    out = _run(root, ["log", range_arg, f"--pretty=format:{_LOG_FORMAT}"])
    commits = []
    for record in out.split("\x1e"):
        record = record.strip("\n")
        if not record.strip():
            continue
        parts = record.lstrip("\n").split(_LOG_SEP)
        if len(parts) < 7:
            continue
        commit_hash, short_hash, author_name, author_email, date, subject, body = parts[:7]
        commits.append(
            {
                "hash": commit_hash,
                "short_hash": short_hash,
                "author_name": author_name,
                "author_email": author_email,
                "date": date,
                "subject": subject,
                "body": body.strip("\n"),
            }
        )
    return commits


def diff_since(root: Path, ref: str, unified: int = 3, paths: list[str] | None = None) -> str:
    """Unified diff of the working tree against `ref` (e.g. `main`, a tag, a sha)."""
    if not is_git_repo(root):
        raise GitError(f"{root} is not a git repository")
    args = ["diff", f"-U{unified}", ref, "--"]
    if paths:
        args.extend(paths)
    return _run(root, args)


def latest_tag(root: Path) -> str | None:
    if not is_git_repo(root):
        return None
    try:
        out = _run(root, ["describe", "--tags", "--abbrev=0"])
        return out.strip() or None
    except GitError:
        return None


def is_clean(root: Path) -> bool | None:
    if not is_git_repo(root):
        return None
    try:
        out = _run(root, ["status", "--porcelain"])
        return len(out.strip()) == 0
    except GitError:
        return None
