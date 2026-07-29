from __future__ import annotations

import subprocess

import pytest

from devtools.core.hotspots_engine import compute_hotspots
from devtools.core.ignore_rules import IgnoreRules
from devtools.utils.git import GitError


def _rules(root):
    return IgnoreRules.build(root, base_ignored_dirs=["node_modules", "__pycache__"])


def _git(root, *args):
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def test_compute_hotspots_ranks_frequently_changed_complex_file_first(git_repo):
    # src/auth.py has 3 functions (complexity ~3); bump its churn well above
    # everything else in the fixture.
    for i in range(3):
        (git_repo / "src" / "auth.py").write_text(
            (git_repo / "src" / "auth.py").read_text() + f"\n# churn {i}\n"
        )
        _git(git_repo, "add", "-A")
        _git(git_repo, "commit", "-q", "-m", f"touch auth {i}")

    hotspots = compute_hotspots(git_repo, _rules(git_repo))
    assert hotspots
    assert hotspots[0].rel_path == "src/auth.py"
    assert hotspots[0].churn == 4  # initial commit + 3 touches
    assert hotspots[0].complexity_is_estimated is False


def test_compute_hotspots_excludes_untouched_files(git_repo):
    # A since-window entirely in the future can't match any real commit.
    hotspots = compute_hotspots(git_repo, _rules(git_repo), since="2099-01-01")
    assert hotspots == []


def test_compute_hotspots_estimates_complexity_for_non_python_files(git_repo):
    (git_repo / "README.md").write_text("# hello\nworld\n")
    _git(git_repo, "add", "-A")
    _git(git_repo, "commit", "-q", "-m", "add readme")

    hotspots = compute_hotspots(git_repo, _rules(git_repo))
    readme = next((h for h in hotspots if h.rel_path == "README.md"), None)
    assert readme is not None
    assert readme.complexity_is_estimated is True


def test_compute_hotspots_raises_on_non_repo(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n")
    with pytest.raises(GitError):
        compute_hotspots(tmp_path, _rules(tmp_path))
