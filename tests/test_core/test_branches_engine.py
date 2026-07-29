from __future__ import annotations

import subprocess
from datetime import datetime, timedelta, timezone

from devtools.core.branches_engine import find_stale_branches, list_branch_info


def _git(root, *args):
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def test_list_branch_info_marks_current_branch(git_repo):
    infos = list_branch_info(git_repo)
    assert len(infos) == 1
    assert infos[0].is_current is True
    assert infos[0].age_days is not None
    assert infos[0].age_days >= 0


def test_find_stale_branches_excludes_current_branch(git_repo):
    # The only branch is current -> never "stale" regardless of age.
    assert find_stale_branches(git_repo, days=0) == []


def test_find_stale_branches_flags_old_unmerged_branch(git_repo):
    _git(git_repo, "checkout", "-q", "-b", "old-feature")
    (git_repo / "src" / "old.py").write_text("x = 1\n")
    _git(git_repo, "add", "-A")
    # Backdate the commit so it reads as old without waiting real time.
    old_date = (datetime.now(timezone.utc) - timedelta(days=200)).isoformat()
    subprocess.run(
        ["git", "commit", "-q", "-m", "old work", f"--date={old_date}"],
        cwd=git_repo,
        check=True,
        capture_output=True,
        env={"GIT_COMMITTER_DATE": old_date, "PATH": "/usr/bin:/bin"},
    )
    _git(git_repo, "checkout", "-q", "-")

    stale = find_stale_branches(git_repo, days=90)
    names = {b.name for b in stale}
    assert "old-feature" in names
    stale_branch = next(b for b in stale if b.name == "old-feature")
    assert stale_branch.merged is False
    assert stale_branch.age_days >= 190


def test_find_stale_branches_empty_when_recent(git_repo):
    _git(git_repo, "checkout", "-q", "-b", "fresh-feature")
    (git_repo / "src" / "fresh.py").write_text("x = 1\n")
    _git(git_repo, "add", "-A")
    _git(git_repo, "commit", "-q", "-m", "fresh work")
    _git(git_repo, "checkout", "-q", "-")

    assert find_stale_branches(git_repo, days=90) == []