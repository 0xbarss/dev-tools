from __future__ import annotations

from devtools.utils import git as gitmod


def test_is_git_repo(git_repo, tmp_path):
    assert gitmod.is_git_repo(git_repo) is True
    assert gitmod.is_git_repo(tmp_path / "not_a_repo") is False


def test_current_branch(git_repo):
    branch = gitmod.current_branch(git_repo)
    assert branch in ("main", "master")  # depends on the user's git default


def test_is_clean_true_right_after_commit(git_repo):
    assert gitmod.is_clean(git_repo) is True


def test_is_clean_false_after_edit(git_repo):
    (git_repo / "src" / "main.py").write_text("# changed\n")
    assert gitmod.is_clean(git_repo) is False


def test_changed_files_since_detects_new_commit(git_repo):
    import subprocess

    base_ref = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=git_repo, capture_output=True, text=True
    ).stdout.strip()

    (git_repo / "src" / "new_file.py").write_text("x = 1\n")
    subprocess.run(["git", "add", "-A"], cwd=git_repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "add new file"], cwd=git_repo, check=True, capture_output=True
    )

    changed = gitmod.changed_files_since(git_repo, base_ref)
    rel = {p.relative_to(git_repo).as_posix() for p in changed}
    assert "src/new_file.py" in rel


def test_changed_files_since_raises_on_non_repo(tmp_path):
    import pytest

    with pytest.raises(gitmod.GitError):
        gitmod.changed_files_since(tmp_path, "HEAD")