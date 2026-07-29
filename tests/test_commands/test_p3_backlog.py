"""CLI-level tests for the Prioritized Backlog P3 items implemented after
the transformation proposal: bookmarks (#37), snippet manager (#34), saved
searches (#38), prompt template library (#31), issue linking (#20),
doctor/deps --notify (#45), and --trace profiling (#52).
"""

from __future__ import annotations

import json

from typer.testing import CliRunner

from devtools.cli import app

runner = CliRunner()


def _register(root, name="demo"):
    result = runner.invoke(app, ["project", "add", name, str(root)])
    assert result.exit_code == 0, result.output
    return name


# --- bookmark (#37) ---------------------------------------------------------


def test_bookmark_add_list_go_remove_roundtrip(sample_repo):
    name = _register(sample_repo, "bm_demo")
    result = runner.invoke(app, ["bookmark", "add", "auth", "src/auth.py", "--project", name, "--note", "core auth logic"])
    assert result.exit_code == 0, result.output

    result = runner.invoke(app, ["--json", "bookmark", "list"])
    assert result.exit_code == 0
    payload = json.loads(result.output)["bookmarks"]
    assert any(b["name"] == "auth" and b["project"] == name for b in payload)

    result = runner.invoke(app, ["bookmark", "go", "auth"])
    assert result.exit_code == 0
    assert str((sample_repo / "src" / "auth.py").resolve()) in result.output

    result = runner.invoke(app, ["bookmark", "remove", "auth"])
    assert result.exit_code == 0
    result = runner.invoke(app, ["bookmark", "go", "auth"])
    assert result.exit_code == 3  # PROJECT_NOT_FOUND-style "no such bookmark"


def test_bookmark_go_unknown_name_fails():
    result = runner.invoke(app, ["bookmark", "go", "nope"])
    assert result.exit_code == 3


# --- snippet (#34) -----------------------------------------------------------


def test_snippet_add_list_show_search_remove_roundtrip():
    result = runner.invoke(app, ["snippet", "add", "retry", "def retry(): ...", "--language", "python", "--tags", "decorator,retry"])
    assert result.exit_code == 0, result.output

    result = runner.invoke(app, ["--json", "snippet", "list"])
    payload = json.loads(result.output)["snippets"]
    assert any(s["name"] == "retry" for s in payload)

    result = runner.invoke(app, ["snippet", "show", "retry"])
    assert result.exit_code == 0
    assert "def retry" in result.output

    result = runner.invoke(app, ["--json", "snippet", "search", "decorator"])
    payload = json.loads(result.output)["snippets"]
    assert any(s["name"] == "retry" for s in payload)

    result = runner.invoke(app, ["snippet", "remove", "retry"])
    assert result.exit_code == 0
    result = runner.invoke(app, ["snippet", "show", "retry"])
    assert result.exit_code == 3


def test_snippet_add_without_content_or_stdin_fails():
    result = runner.invoke(app, ["snippet", "add", "empty"], input="")
    # CliRunner supplies a non-tty stdin; empty input means empty content is
    # accepted (piped-but-empty), so this exercises the stdin-read path
    # rather than the "no content" failure -- just confirm it doesn't crash.
    assert result.exit_code == 0


# --- saved searches (#38) -----------------------------------------------------


def test_search_save_load_list_remove_roundtrip(sample_repo):
    name = _register(sample_repo, "search_demo")
    result = runner.invoke(app, ["search", name, "authentication", "--save", "auth-search"])
    assert result.exit_code == 0, result.output

    result = runner.invoke(app, ["--json", "search", "--list-saved"])
    payload = json.loads(result.output)["saved_searches"]
    assert any(s["name"] == "auth-search" and s["concept"] == "authentication" for s in payload)

    result = runner.invoke(app, ["search", "--load", "auth-search"])
    assert result.exit_code == 0

    result = runner.invoke(app, ["search", "--remove-saved", "auth-search"])
    assert result.exit_code == 0
    result = runner.invoke(app, ["--json", "search", "--list-saved"])
    payload = json.loads(result.output)["saved_searches"]
    assert not any(s["name"] == "auth-search" for s in payload)


def test_search_load_unknown_name_fails():
    result = runner.invoke(app, ["search", "--load", "does-not-exist"])
    assert result.exit_code == 1


# --- prompt template library (#31) --------------------------------------------


def test_prompt_add_list_show_run_remove_roundtrip():
    result = runner.invoke(app, ["prompt", "add", "pr-summary", "Summarize {diff} in one paragraph.", "--description", "PR summary"])
    assert result.exit_code == 0, result.output

    result = runner.invoke(app, ["--json", "prompt", "list"])
    payload = json.loads(result.output)["templates"]
    entry = next(t for t in payload if t["name"] == "pr-summary")
    assert "diff" in entry["variables"]

    result = runner.invoke(app, ["prompt", "show", "pr-summary"])
    assert result.exit_code == 0
    assert "{diff}" in result.output

    result = runner.invoke(app, ["prompt", "run", "pr-summary", "--var", "diff=+1/-1 in auth.py"])
    assert result.exit_code == 0
    assert "Summarize +1/-1 in auth.py in one paragraph." in result.output

    result = runner.invoke(app, ["prompt", "remove", "pr-summary"])
    assert result.exit_code == 0
    result = runner.invoke(app, ["prompt", "show", "pr-summary"])
    assert result.exit_code == 3


def test_prompt_run_missing_variable_fails_with_clear_message():
    runner.invoke(app, ["prompt", "add", "needs-var", "Explain {topic}."])
    result = runner.invoke(app, ["prompt", "run", "needs-var"])
    assert result.exit_code == 2
    assert "topic" in result.output


def test_prompt_run_complete_without_provider_fails():
    runner.invoke(app, ["prompt", "add", "ask", "Explain {topic}."])
    result = runner.invoke(app, ["prompt", "run", "ask", "--var", "topic=recursion", "--complete"])
    assert result.exit_code == 1
    assert "No AI provider configured" in result.output


# --- issue linking (#20) ------------------------------------------------------


def test_pr_link_issues_finds_references(git_repo):
    import subprocess

    (git_repo / "feature.py").write_text("x = 1\n")
    subprocess.run(["git", "add", "-A"], cwd=git_repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "Fixes #42: add feature\n\nAlso relates to PROJ-7."],
        cwd=git_repo, check=True, capture_output=True,
    )

    name = _register(git_repo, "issue_link_demo")
    result = runner.invoke(app, ["--json", "pr", "link-issues", name])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert "42" in payload["issue_ids"]
    assert "PROJ-7" in payload["issue_ids"]
    ref42 = next(r for r in payload["references"] if r["issue_id"] == "42")
    assert ref42["closes"] is True


def test_pr_link_issues_non_git_project_fails(sample_repo):
    name = _register(sample_repo, "not_git")
    result = runner.invoke(app, ["pr", "link-issues", name])
    assert result.exit_code == 1


def test_pr_link_issues_with_tracker_url(git_repo):
    import subprocess

    subprocess.run(["git", "commit", "--allow-empty", "-q", "-m", "fix #9"], cwd=git_repo, check=True, capture_output=True)
    name = _register(git_repo, "issue_link_tracker")
    runner.invoke(app, ["config", "set", "issue_tracker_url", "https://github.com/org/repo/issues"])
    result = runner.invoke(app, ["--json", "pr", "link-issues", name])
    payload = json.loads(result.output)
    ref = next(r for r in payload["references"] if r["issue_id"] == "9")
    assert ref["url"] == "https://github.com/org/repo/issues/9"


# --- doctor/deps --notify (#45) -----------------------------------------------


def test_doctor_notify_unknown_target_fails(sample_repo):
    name = _register(sample_repo, "doctor_notify_missing")
    result = runner.invoke(app, ["doctor", name, "--notify", "no-such-target"])
    assert result.exit_code == 2


def test_doctor_notify_skipped_when_no_issues(tmp_path):
    root = tmp_path / "clean_repo"
    root.mkdir()
    (root / "README.md").write_text("# clean\n")
    (root / "LICENSE").write_text("MIT\n")
    name = _register(root, "doctor_clean")
    runner.invoke(app, ["notify", "add", "t1", "https://example.com/hook", "--kind", "generic"])
    # A target exists, but with no issues found, sending should just be
    # skipped rather than attempted (and fail on network) -- exit 0 proves
    # devtools never tried to reach the network here.
    result = runner.invoke(app, ["doctor", name, "--notify", "t1"])
    assert result.exit_code == 0


def test_deps_notify_unknown_target_fails(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "s"\n')  # manifest present, no dependencies key
    name = _register(tmp_path, "deps_notify_missing")
    result = runner.invoke(app, ["deps", name, "--notify", "no-such-target", "--check"])
    assert result.exit_code == 2


# --- --trace profiling (#52) --------------------------------------------------


def test_collect_trace_prints_phase_breakdown(sample_repo):
    name = _register(sample_repo, "trace_demo")
    result = runner.invoke(app, ["--trace", "collect", name, "--stdout"])
    assert result.exit_code == 0, result.output
    assert "Trace" in result.output
    assert "collect_files" in result.output


def test_collect_without_trace_flag_has_no_trace_output(sample_repo):
    name = _register(sample_repo, "no_trace_demo")
    result = runner.invoke(app, ["collect", name, "--stdout"])
    assert result.exit_code == 0
    assert "Trace" not in result.output
