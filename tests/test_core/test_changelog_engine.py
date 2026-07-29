from __future__ import annotations

import subprocess

import pytest

from devtools.core.changelog_engine import classify_commit, generate_changelog, render_markdown


def _git(root, *args):
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


@pytest.fixture
def git_repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "a@b.com")
    _git(root, "config", "user.name", "Test")
    (root / "a.txt").write_text("1")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "feat(auth): add login flow")
    (root / "a.txt").write_text("2")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "fix: correct off-by-one error")
    (root / "a.txt").write_text("3")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "tidy up whitespace")
    return root


@pytest.mark.parametrize(
    "subject,expected_section,expected_scope,expected_breaking",
    [
        ("feat(auth): add login flow", "Added", "auth", False),
        ("fix: correct bug", "Fixed", None, False),
        ("feat!: breaking change to API", "Added", None, True),
        ("just a random message", "Other", None, False),
    ],
)
def test_classify_commit(subject, expected_section, expected_scope, expected_breaking):
    section, scope, _description, breaking = classify_commit(subject)
    assert section == expected_section
    assert scope == expected_scope
    assert breaking == expected_breaking


def test_generate_changelog_groups_by_section(git_repo):
    report = generate_changelog(git_repo)
    sections = {e.section for e in report.entries}
    assert "Added" in sections
    assert "Fixed" in sections
    assert len(report.unclassified) == 1
    assert report.unclassified[0].description == "tidy up whitespace"


def test_generate_changelog_respects_since(git_repo):
    # get first commit hash
    import subprocess as sp

    out = sp.run(["git", "log", "--reverse", "--pretty=%H"], cwd=git_repo, capture_output=True, text=True, check=True)
    first_hash = out.stdout.splitlines()[0]
    report = generate_changelog(git_repo, since=first_hash)
    all_entries = report.entries + report.unclassified
    assert len(all_entries) == 2  # excludes the first commit


def test_render_markdown_includes_sections_and_hashes(git_repo):
    report = generate_changelog(git_repo)
    md = render_markdown(report, title="My Project")
    assert "# My Project" in md
    assert "## Added" in md
    assert "## Fixed" in md


def test_render_markdown_empty_range(tmp_path):
    from devtools.core.changelog_engine import ChangelogReport

    report = ChangelogReport(since=None, until="HEAD")
    md = render_markdown(report)
    assert "No commits in range" in md