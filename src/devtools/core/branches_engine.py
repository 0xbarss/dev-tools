"""`devtools branches --stale` — finds branches safe to delete (backlog #17,
P1). A branch is "stale" when its last commit is older than a configurable
age threshold and it isn't the branch currently checked out. Merged status
(already computed by `utils/git.list_branches`) is reported alongside so
callers can distinguish "stale and merged -- safe to delete" from "stale
and unmerged -- needs a human look" without this module making that call
for them.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from devtools.utils import git as gitmod

DEFAULT_STALE_DAYS = 90


@dataclass
class BranchInfo:
    name: str
    last_commit_date: str
    last_author: str
    last_subject: str
    merged: bool
    is_current: bool
    age_days: int | None


def _parse_iso(date_str: str) -> datetime | None:
    try:
        return datetime.fromisoformat(date_str)
    except ValueError:
        return None


def list_branch_info(root: Path, days: int = DEFAULT_STALE_DAYS) -> list[BranchInfo]:
    """Every local branch with computed age; `age_days` is None if the
    branch's date couldn't be parsed (defensive -- git's iso-strict format
    is stable, but this keeps a malformed entry from crashing the report)."""
    current = gitmod.current_branch(root)
    now = datetime.now(timezone.utc)
    out = []
    for b in gitmod.list_branches(root):
        parsed = _parse_iso(b["last_commit_date"])
        age_days = (now - parsed).days if parsed else None
        out.append(
            BranchInfo(
                name=b["name"],
                last_commit_date=b["last_commit_date"],
                last_author=b["last_author"],
                last_subject=b["last_subject"],
                merged=b["merged"],
                is_current=(b["name"] == current),
                age_days=age_days,
            )
        )
    return out


def find_stale_branches(root: Path, days: int = DEFAULT_STALE_DAYS) -> list[BranchInfo]:
    """Branches older than `days` (by last commit), excluding the branch
    that's currently checked out -- you can't (and shouldn't) delete that
    one out from under yourself."""
    return [
        b
        for b in list_branch_info(root, days=days)
        if not b.is_current and b.age_days is not None and b.age_days >= days
    ]
