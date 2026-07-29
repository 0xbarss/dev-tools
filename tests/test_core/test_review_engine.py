from __future__ import annotations

import subprocess

import pytest

from devtools.core.review_engine import review, render_markdown, ReviewReport, ReviewComment


def _git(root, *args):
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


@pytest.fixture
def git_repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "a@b.com")
    _git(root, "config", "user.name", "Test")
    (root / "a.py").write_text("def f():\n    return 1\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "initial")
    (root / "a.py").write_text("def f():\n    return 2\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "change")
    return root


class FakeClient:
    def __init__(self, response):
        self._response = response

    def complete(self, prompt, system=None):
        self.last_prompt = prompt
        return self._response


def test_review_parses_well_formed_json(git_repo):
    response = '{"summary": "looks fine", "comments": [{"file": "a.py", "line": 2, "severity": "bug", "comment": "check this"}]}'
    client = FakeClient(response)
    report = review(git_repo, client, since="HEAD~1")
    assert report.summary == "looks fine"
    assert len(report.comments) == 1
    assert report.comments[0].file == "a.py"
    assert report.raw_text is None


def test_review_handles_fenced_json(git_repo):
    response = '```json\n{"summary": "ok", "comments": []}\n```'
    client = FakeClient(response)
    report = review(git_repo, client, since="HEAD~1")
    assert report.summary == "ok"


def test_review_falls_back_to_raw_text_on_bad_json(git_repo):
    client = FakeClient("not json at all, just prose")
    report = review(git_repo, client, since="HEAD~1")
    assert report.raw_text == "not json at all, just prose"
    assert report.comments == []


def test_review_raises_when_no_diff(git_repo):
    client = FakeClient('{"summary": "x", "comments": []}')
    with pytest.raises(ValueError, match="nothing to review"):
        review(git_repo, client, since="HEAD")


def test_render_markdown_with_comments():
    report = ReviewReport(since="main", summary="Solid change.", comments=[ReviewComment(file="a.py", line=2, severity="bug", comment="off by one")])
    md = render_markdown(report, "myproj")
    assert "Suggestions, not blockers" in md
    assert "a.py:2" in md
    assert "off by one" in md


def test_render_markdown_with_raw_text_fallback():
    report = ReviewReport(since="main", summary="(unstructured response — see raw_text)", raw_text="free text review")
    md = render_markdown(report, "myproj")
    assert "free text review" in md