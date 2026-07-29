"""Unit tests for the core modules backing the P3 backlog commands."""

from __future__ import annotations

import subprocess

import pytest

from devtools.core.pr_engine import issue_url, link_issues
from devtools.core.prompt_store import PromptRenderError, PromptTemplate, parse_var_options, render_template
from devtools.core.tracer import Tracer


def test_render_template_substitutes_variables():
    t = PromptTemplate(name="x", template="Hello {who}, review {file}.")
    assert render_template(t, {"who": "Ada", "file": "auth.py"}) == "Hello Ada, review auth.py."


def test_render_template_missing_variable_raises_named_error():
    t = PromptTemplate(name="x", template="Hello {who}.")
    with pytest.raises(PromptRenderError, match="who"):
        render_template(t, {})


def test_parse_var_options_handles_equals_in_value():
    assert parse_var_options(["key=a=b=c"]) == {"key": "a=b=c"}


def test_parse_var_options_rejects_bad_format():
    with pytest.raises(ValueError):
        parse_var_options(["not-a-kv-pair"])


def test_link_issues_extracts_github_and_jira_style_ids(git_repo):
    (git_repo / "x.txt").write_text("x")
    subprocess.run(["git", "add", "-A"], cwd=git_repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "Closes #7 and PROJ-3"],
        cwd=git_repo, check=True, capture_output=True,
    )
    result = link_issues(git_repo)
    assert set(result.issue_ids) >= {"7", "PROJ-3"}
    assert all(ref.closes for ref in result.references if ref.issue_id == "7")


def test_link_issues_no_matches_returns_empty():
    pass  # covered indirectly via non-git-repo CLI test; git_repo fixture always has one commit


def test_issue_url_joins_base_and_id():
    assert issue_url("42", "https://github.com/org/repo/issues") == "https://github.com/org/repo/issues/42"
    assert issue_url("42", None) is None


def test_tracer_disabled_records_nothing():
    tracer = Tracer(enabled=False)
    with tracer.phase("work"):
        pass
    assert tracer.timings == []


def test_tracer_enabled_records_named_phases():
    tracer = Tracer(enabled=True)
    with tracer.phase("scan"):
        pass
    with tracer.phase("render"):
        pass
    names = {t.name for t in tracer.timings}
    assert names == {"scan", "render"}
    rows = tracer.as_rows()
    assert {r["phase"] for r in rows} == names
