from __future__ import annotations

import json
import subprocess

from typer.testing import CliRunner

from devtools.cli import app

runner = CliRunner()


def _register(root, name="demo"):
    result = runner.invoke(app, ["project", "add", name, str(root)])
    assert result.exit_code == 0, result.output
    return name


def test_lint_reports_no_ecosystem_for_empty_project(tmp_path):
    name = _register(tmp_path, "empty_lint")
    result = runner.invoke(app, ["lint", name])
    assert result.exit_code == 0
    assert "nothing to lint" in result.output


def test_lint_json_output_shape(sample_repo):
    name = _register(sample_repo, "lint_json")
    result = runner.invoke(app, ["--json", "lint", name])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert "findings" in payload
    assert "skipped" in payload


def test_changelog_renders_markdown(git_repo):
    name = _register(git_repo, "changelog_demo")
    result = runner.invoke(app, ["changelog", name])
    assert result.exit_code == 0
    assert "Changelog" in result.output


def test_changelog_json_output(git_repo):
    name = _register(git_repo, "changelog_json")
    result = runner.invoke(app, ["--json", "changelog", name])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert "entries" in payload


def test_changelog_fails_cleanly_on_non_git_project(sample_repo):
    name = _register(sample_repo, "changelog_nogit")
    result = runner.invoke(app, ["changelog", name])
    assert result.exit_code != 0


def test_explain_fails_cleanly_without_ai_provider(sample_repo):
    name = _register(sample_repo, "explain_demo")
    result = runner.invoke(app, ["explain", name, "src/auth.py"])
    assert result.exit_code != 0
    assert "No AI provider configured" in result.output


def test_review_fails_cleanly_without_ai_provider(git_repo):
    name = _register(git_repo, "review_demo")
    (git_repo / "src" / "auth.py").write_text("def login(user, password):\n    return True\n")
    result = runner.invoke(app, ["review", name, "--since", "HEAD"])
    assert result.exit_code != 0
    assert "No AI provider configured" in result.output


def test_index_build_and_status(sample_repo):
    name = _register(sample_repo, "index_demo")
    build_result = runner.invoke(app, ["index", "build", name])
    assert build_result.exit_code == 0

    status_result = runner.invoke(app, ["--json", "index", "status", name])
    assert status_result.exit_code == 0
    payload = json.loads(status_result.output)
    assert payload["files_indexed"] > 0
    assert payload["fresh"] is True


def test_index_clear(sample_repo):
    name = _register(sample_repo, "index_clear_demo")
    runner.invoke(app, ["index", "build", name])
    result = runner.invoke(app, ["index", "clear", name])
    assert result.exit_code == 0
    assert "Deleted index" in result.output


def test_search_semantic_falls_back_with_warning_when_no_index(sample_repo):
    name = _register(sample_repo, "search_no_index")
    result = runner.invoke(app, ["search", name, "authentication", "--semantic"])
    assert result.exit_code == 0
    assert "No semantic index found" in result.output


def test_search_semantic_after_build_index(sample_repo):
    name = _register(sample_repo, "search_with_index")
    build_result = runner.invoke(app, ["search", name, "--build-index"])
    assert build_result.exit_code == 0
    result = runner.invoke(app, ["search", name, "authentication", "--semantic"])
    assert result.exit_code == 0
    assert "auth.py" in result.output


def test_mcp_serve_help_lists_transport_option():
    result = runner.invoke(app, ["mcp-serve", "--help"])
    assert result.exit_code == 0
    assert "--transport" in result.output
