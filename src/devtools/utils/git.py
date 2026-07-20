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


def is_clean(root: Path) -> bool | None:
    if not is_git_repo(root):
        return None
    try:
        out = _run(root, ["status", "--porcelain"])
        return len(out.strip()) == 0
    except GitError:
        return None
