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


def checkout_branch(root: Path, branch: str) -> None:
    """`git checkout <branch>` (used by `devtools snapshot restore --checkout`,
    backlog #32). Deliberately narrow: doesn't create branches, doesn't force,
    doesn't stash -- if the checkout would fail, the caller sees git's own
    error rather than devtools silently doing something more aggressive."""
    if not is_git_repo(root):
        raise GitError(f"{root} is not a git repository")
    _run(root, ["checkout", branch])


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


def numstat_since(root: Path, ref: str, paths: list[str] | None = None) -> list[dict]:
    """Per-file added/removed line counts for the working tree vs `ref`
    (used by `devtools pr describe`, backlog #19) -- the diff-range sibling
    of `author_numstat`'s per-commit-log numstat."""
    if not is_git_repo(root):
        raise GitError(f"{root} is not a git repository")
    args = ["diff", "--numstat", ref, "--"]
    if paths:
        args.extend(paths)
    out = _run(root, args)
    files = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        added, deleted, path = parts
        files.append(
            {
                "path": path,
                "additions": int(added) if added.isdigit() else 0,
                "deletions": int(deleted) if deleted.isdigit() else 0,
                "binary": not added.isdigit(),
            }
        )
    return files


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


def blame_line_counts(root: Path, rel_path: str) -> dict[str, int]:
    """Line-count-by-author for a single file, via `git blame --line-porcelain`.

    Returns {} for files git can't blame (untracked, binary, deleted, etc.)
    rather than raising -- callers (owners_engine) treat that as "no
    ownership data" for the file, not a hard failure.
    """
    if not is_git_repo(root):
        raise GitError(f"{root} is not a git repository")
    try:
        out = _run(root, ["blame", "--line-porcelain", "--", rel_path])
    except GitError:
        return {}
    counts: dict[str, int] = {}
    for line in out.splitlines():
        if line.startswith("author "):
            author = line[len("author ") :].strip()
            counts[author] = counts.get(author, 0) + 1
    return counts


def file_commit_counts(root: Path, rel_paths: list[str] | None = None, since: str | None = None) -> dict[str, int]:
    """Number of commits touching each file (churn), via `git log --name-only`.

    `since` is a git-recognized date expression (e.g. "90 days ago"). With
    `rel_paths=None`, every file touched in the range is counted; pass an
    explicit list to restrict the log walk to those paths (faster on large
    repos when the caller already knows the candidate set).
    """
    if not is_git_repo(root):
        raise GitError(f"{root} is not a git repository")
    args = ["log", "--name-only", "--pretty=format:", "--no-color"]
    if since:
        args.extend(["--since", since])
    if rel_paths:
        args.append("--")
        args.extend(rel_paths)
    out = _run(root, args)
    counts: dict[str, int] = {}
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        counts[line] = counts.get(line, 0) + 1
    return counts


def author_numstat(root: Path, since: str | None = None, until: str = "HEAD") -> list[dict]:
    """Per-commit author + line-change stats, for `devtools contributors`
    (backlog #16). `since` accepts either a git date expression ("90 days
    ago", "2024-01-01") or a ref, since `git log --since` happily ignores
    an argument that isn't a recognizable date -- callers that want a
    strict ref..until range should use `log_commits` instead.
    """
    if not is_git_repo(root):
        raise GitError(f"{root} is not a git repository")
    fmt = "\x1e" + _LOG_SEP.join(["%H", "%an", "%ae", "%aI"])
    args = ["log", until, f"--pretty=format:{fmt}", "--numstat"]
    if since:
        args.extend(["--since", since])
    out = _run(root, args)

    commits = []
    for record in out.split("\x1e"):
        record = record.strip("\n")
        if not record.strip():
            continue
        lines = record.lstrip("\n").splitlines()
        header = lines[0].split(_LOG_SEP)
        if len(header) < 4:
            continue
        commit_hash, author_name, author_email, date = header[:4]
        additions = 0
        deletions = 0
        files_changed = 0
        for line in lines[1:]:
            parts = line.split("\t")
            if len(parts) != 3:
                continue
            added, deleted, _path = parts
            files_changed += 1
            if added.isdigit():
                additions += int(added)
            if deleted.isdigit():
                deletions += int(deleted)
        commits.append(
            {
                "hash": commit_hash,
                "author_name": author_name,
                "author_email": author_email,
                "date": date,
                "additions": additions,
                "deletions": deletions,
                "files_changed": files_changed,
            }
        )
    return commits


def show_commit(root: Path, sha: str, unified: int = 3) -> dict:
    """A single commit's metadata + patch text, for `devtools commit explain <sha>`."""
    if not is_git_repo(root):
        raise GitError(f"{root} is not a git repository")
    fmt = _LOG_SEP.join(["%H", "%h", "%an", "%ae", "%aI", "%s", "%b"])
    meta_out = _run(root, ["show", "-s", f"--pretty=format:{fmt}", sha])
    parts = meta_out.split(_LOG_SEP)
    if len(parts) < 7:
        raise GitError(f"Could not read commit metadata for {sha!r}")
    commit_hash, short_hash, author_name, author_email, date, subject, body = parts[:7]
    patch = _run(root, ["show", f"-U{unified}", "--pretty=format:", sha])
    return {
        "hash": commit_hash,
        "short_hash": short_hash,
        "author_name": author_name,
        "author_email": author_email,
        "date": date,
        "subject": subject,
        "body": body.strip("\n"),
        "patch": patch.strip("\n"),
    }


def list_branches(root: Path, remote: bool = False) -> list[dict]:
    """Local (or remote-tracking, with `remote=True`) branches with their
    last commit date/author/subject and whether they're already merged into
    the current HEAD -- the raw material for `devtools branches --stale`.
    """
    if not is_git_repo(root):
        raise GitError(f"{root} is not a git repository")
    ref_prefix = "refs/remotes/" if remote else "refs/heads/"
    fmt = _LOG_SEP.join(["%(refname:short)", "%(committerdate:iso-strict)", "%(authorname)", "%(subject)"])
    out = _run(root, ["for-each-ref", f"--format={fmt}", ref_prefix])

    try:
        merged_out = _run(root, ["branch", "--format=%(refname:short)", "--merged"])
        merged = {line.strip() for line in merged_out.splitlines() if line.strip()}
    except GitError:
        merged = set()

    branches = []
    for line in out.splitlines():
        if not line.strip():
            continue
        parts = line.split(_LOG_SEP)
        if len(parts) < 4:
            continue
        name, date, author, subject = parts[:4]
        branches.append(
            {
                "name": name,
                "last_commit_date": date,
                "last_author": author,
                "last_subject": subject,
                "merged": name in merged,
            }
        )
    return branches
