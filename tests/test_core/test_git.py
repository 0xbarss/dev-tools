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



def test_log_commits_returns_structured_entries(git_repo):
    import subprocess

    (git_repo / "src" / "another.py").write_text("y = 2\n")
    subprocess.run(["git", "add", "-A"], cwd=git_repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "feat: add another file"], cwd=git_repo, check=True, capture_output=True)

    commits = gitmod.log_commits(git_repo)
    assert len(commits) >= 2
    assert commits[0]["subject"] == "feat: add another file"
    assert set(commits[0]) == {"hash", "short_hash", "author_name", "author_email", "date", "subject", "body"}


def test_log_commits_respects_since(git_repo):
    import subprocess

    first_hash = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=git_repo, capture_output=True, text=True
    ).stdout.strip()
    (git_repo / "src" / "another.py").write_text("y = 2\n")
    subprocess.run(["git", "add", "-A"], cwd=git_repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "feat: add another file"], cwd=git_repo, check=True, capture_output=True)

    commits = gitmod.log_commits(git_repo, since=first_hash)
    assert len(commits) == 1
    assert commits[0]["subject"] == "feat: add another file"


def test_log_commits_raises_on_non_repo(tmp_path):
    import pytest

    with pytest.raises(gitmod.GitError):
        gitmod.log_commits(tmp_path)


def test_diff_since_shows_changes(git_repo):
    (git_repo / "src" / "main.py").write_text("# changed content\n")
    diff = gitmod.diff_since(git_repo, "HEAD")
    assert "changed content" in diff


def test_diff_since_empty_when_no_changes(git_repo):
    diff = gitmod.diff_since(git_repo, "HEAD")
    assert diff.strip() == ""


def test_diff_since_raises_on_non_repo(tmp_path):
    import pytest

    with pytest.raises(gitmod.GitError):
        gitmod.diff_since(tmp_path, "HEAD")


def test_latest_tag_none_when_no_tags(git_repo):
    assert gitmod.latest_tag(git_repo) is None


def test_latest_tag_returns_tag_name(git_repo):
    import subprocess

    subprocess.run(["git", "tag", "v1.0.0"], cwd=git_repo, check=True, capture_output=True)
    assert gitmod.latest_tag(git_repo) == "v1.0.0"


def test_latest_tag_none_on_non_repo(tmp_path):
    assert gitmod.latest_tag(tmp_path) is None


def test_blame_line_counts_attributes_every_line_to_the_committer(git_repo):
    counts = gitmod.blame_line_counts(git_repo, "src/auth.py")
    assert sum(counts.values()) == len((git_repo / "src" / "auth.py").read_text().splitlines())
    assert set(counts) == {"Test"}


def test_blame_line_counts_empty_for_untracked_file(git_repo):
    (git_repo / "src" / "untracked.py").write_text("x = 1\n")
    assert gitmod.blame_line_counts(git_repo, "src/untracked.py") == {}


def test_blame_line_counts_empty_on_non_repo(tmp_path):
    with __import__("pytest").raises(gitmod.GitError):
        gitmod.blame_line_counts(tmp_path, "whatever.py")


def test_file_commit_counts_tracks_churn(git_repo):
    import subprocess

    (git_repo / "src" / "main.py").write_text("# edited\n")
    subprocess.run(["git", "add", "-A"], cwd=git_repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "edit main"], cwd=git_repo, check=True, capture_output=True)

    counts = gitmod.file_commit_counts(git_repo)
    assert counts["src/main.py"] == 2  # initial commit + the edit
    assert counts["src/auth.py"] == 1


def test_file_commit_counts_respects_path_filter(git_repo):
    import subprocess

    (git_repo / "src" / "main.py").write_text("# edited\n")
    subprocess.run(["git", "add", "-A"], cwd=git_repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "edit main"], cwd=git_repo, check=True, capture_output=True)

    counts = gitmod.file_commit_counts(git_repo, rel_paths=["src/auth.py"])
    assert "src/main.py" not in counts
    assert counts["src/auth.py"] == 1


def test_list_branches_reports_current_branch_as_merged(git_repo):
    branches = gitmod.list_branches(git_repo)
    assert len(branches) == 1
    b = branches[0]
    assert b["name"] in ("main", "master")
    assert b["merged"] is True
    assert b["last_subject"] == "initial commit"


def test_list_branches_flags_unmerged_feature_branch(git_repo):
    import subprocess

    subprocess.run(["git", "checkout", "-q", "-b", "feature/unmerged"], cwd=git_repo, check=True, capture_output=True)
    (git_repo / "src" / "feature.py").write_text("x = 1\n")
    subprocess.run(["git", "add", "-A"], cwd=git_repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "wip feature"], cwd=git_repo, check=True, capture_output=True)
    subprocess.run(["git", "checkout", "-q", "-"], cwd=git_repo, check=True, capture_output=True)

    branches = {b["name"]: b for b in gitmod.list_branches(git_repo)}
    assert "feature/unmerged" in branches
    assert branches["feature/unmerged"]["merged"] is False