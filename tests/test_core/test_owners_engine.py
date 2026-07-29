from __future__ import annotations

import subprocess

import pytest

from devtools.core.ignore_rules import IgnoreRules
from devtools.core.owners_engine import compute_ownership
from devtools.utils.git import GitError


def _rules(root):
    return IgnoreRules.build(root, base_ignored_dirs=["node_modules", "__pycache__"])


def test_compute_ownership_attributes_sole_author(git_repo):
    report = compute_ownership(git_repo, _rules(git_repo))
    by_path = {f.rel_path: f for f in report.files}
    assert "src/auth.py" in by_path
    assert by_path["src/auth.py"].top_author == "Test"
    assert by_path["src/auth.py"].top_author_share == 1.0


def test_compute_ownership_skips_untracked_files(git_repo):
    (git_repo / "src" / "untracked.py").write_text("x = 1\n")
    report = compute_ownership(git_repo, _rules(git_repo))
    assert "src/untracked.py" in report.skipped
    assert "src/untracked.py" not in {f.rel_path for f in report.files}


def test_compute_ownership_respects_path_prefix(git_repo):
    report = compute_ownership(git_repo, _rules(git_repo), path_prefix="tests/")
    paths = {f.rel_path for f in report.files}
    assert all(p.startswith("tests/") for p in paths)
    assert "src/auth.py" not in paths


def test_compute_ownership_splits_credit_between_two_authors(git_repo):
    def _git(*args):
        subprocess.run(["git", *args], cwd=git_repo, check=True, capture_output=True)

    _git("config", "user.email", "second@example.com")
    _git("config", "user.name", "Second")
    (git_repo / "src" / "auth.py").write_text(
        (git_repo / "src" / "auth.py").read_text() + "\ndef extra():\n    return 1\n"
    )
    _git("add", "-A")
    _git("commit", "-q", "-m", "add extra function")

    report = compute_ownership(git_repo, _rules(git_repo))
    by_path = {f.rel_path: f for f in report.files}
    auth = by_path["src/auth.py"]
    assert set(auth.authors) == {"Test", "Second"}
    assert auth.top_author == "Test"  # Test still wrote the majority of lines


def test_compute_ownership_raises_on_non_repo(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n")
    with pytest.raises(GitError):
        compute_ownership(tmp_path, _rules(tmp_path))
