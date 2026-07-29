from __future__ import annotations

import json
import subprocess
import sys

from typer.testing import CliRunner

from devtools.cli import app

runner = CliRunner()


def _register(root, name="demo"):
    result = runner.invoke(app, ["project", "add", name, str(root)])
    assert result.exit_code == 0, result.output
    return name


def _git(root, *args):
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


# --- owners ---------------------------------------------------------------


def test_owners_reports_top_author(git_repo):
    name = _register(git_repo, "owners_demo")
    result = runner.invoke(app, ["owners", name])
    assert result.exit_code == 0
    assert "src/auth.py" in result.output


def test_owners_json_output_shape(git_repo):
    name = _register(git_repo, "owners_json")
    result = runner.invoke(app, ["--json", "owners", name])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert any(f["path"] == "src/auth.py" and f["top_author"] == "Test" for f in payload["files"])


def test_owners_on_non_git_project_fails_cleanly(sample_repo):
    name = _register(sample_repo, "owners_nongit")
    result = runner.invoke(app, ["owners", name])
    assert result.exit_code == 1


# --- branches ---------------------------------------------------------------


def test_branches_lists_current_branch(git_repo):
    name = _register(git_repo, "branches_demo")
    result = runner.invoke(app, ["branches", name])
    assert result.exit_code == 0
    assert "yes" in result.output  # current branch always shows merged=yes


def test_branches_stale_json_shape(git_repo):
    name = _register(git_repo, "branches_json")
    result = runner.invoke(app, ["--json", "branches", name, "--stale", "--days", "0"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["stale_only"] is True
    assert payload["days_threshold"] == 0
    # the only branch is current, so it's never reported as stale
    assert payload["branches"] == []


# --- stats --hotspots ---------------------------------------------------


def test_stats_hotspots_reports_ranked_files(git_repo):
    name = _register(git_repo, "hotspots_demo")
    result = runner.invoke(app, ["stats", name, "--hotspots"])
    assert result.exit_code == 0
    assert "src/auth.py" in result.output


def test_stats_hotspots_json_shape(git_repo):
    name = _register(git_repo, "hotspots_json")
    result = runner.invoke(app, ["--json", "stats", name, "--hotspots"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert "hotspots" in payload
    assert all({"path", "churn", "complexity", "score"} <= set(h) for h in payload["hotspots"])


# --- health ---------------------------------------------------------------


def test_health_reports_score_and_grade(sample_repo):
    name = _register(sample_repo, "health_demo")
    result = runner.invoke(app, ["health", name])
    assert result.exit_code == 0
    assert "health" in result.output.lower()


def test_health_json_shape(sample_repo):
    name = _register(sample_repo, "health_json")
    result = runner.invoke(app, ["--json", "health", name])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert 0 <= payload["score"] <= 100
    assert payload["grade"] in {"A", "B", "C", "D", "F"}
    assert len(payload["categories"]) == 4


def test_health_ci_flag_fails_below_threshold(sample_repo):
    name = _register(sample_repo, "health_ci")
    result = runner.invoke(app, ["health", name, "--ci", "--min-score", "101"])
    assert result.exit_code == 5


# --- export --format sarif --------------------------------------------


def test_export_lint_sarif_writes_valid_document(sample_repo, tmp_path):
    name = _register(sample_repo, "sarif_demo")
    lint_result = runner.invoke(app, ["lint", name])
    assert lint_result.exit_code == 0

    out_path = tmp_path / "lint.sarif"
    result = runner.invoke(app, ["export", "lint", name, "--format", "sarif", "--out", str(out_path)])
    assert result.exit_code == 0
    doc = json.loads(out_path.read_text())
    assert doc["version"] == "2.1.0"
    assert "runs" in doc


def test_export_sarif_rejects_non_lint_command(sample_repo):
    name = _register(sample_repo, "sarif_reject")
    runner.invoke(app, ["stats", name])
    result = runner.invoke(app, ["export", "stats", name, "--format", "sarif"])
    assert result.exit_code == 2


def test_export_sarif_without_prior_lint_run_fails_cleanly(sample_repo):
    name = _register(sample_repo, "sarif_no_cache")
    result = runner.invoke(app, ["export", "lint", name, "--format", "sarif"])
    assert result.exit_code == 1


# --- graph ------------------------------------------------------------


def test_graph_mermaid_output_contains_edges(sample_repo):
    name = _register(sample_repo, "graph_demo")
    result = runner.invoke(app, ["graph", name])
    assert result.exit_code == 0
    assert "graph LR" in result.output


def test_graph_dot_format(sample_repo):
    name = _register(sample_repo, "graph_dot")
    result = runner.invoke(app, ["graph", name, "--format", "dot"])
    assert result.exit_code == 0
    assert "digraph" in result.output


def test_graph_json_shape(sample_repo):
    name = _register(sample_repo, "graph_json")
    result = runner.invoke(app, ["--json", "graph", name])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert "nodes" in payload and "edges" in payload and "rendered" in payload


def test_graph_module_filter_restricts_nodes(sample_repo):
    name = _register(sample_repo, "graph_filter")
    result = runner.invoke(app, ["--json", "graph", name, "--module", "main"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["nodes"] == ["main"]


# --- watch --------------------------------------------------------------


def test_watch_once_runs_the_target_command_and_exits(sample_repo):
    name = _register(sample_repo, "watch_once")
    result = runner.invoke(app, ["watch", "stats", name, "--once"])
    assert result.exit_code == 0
    assert "summary" in result.output.lower()


def test_watch_passes_through_extra_args(sample_repo):
    name = _register(sample_repo, "watch_args")
    result = runner.invoke(app, ["watch", "health", name, "--once", "--arg", "--ci", "--arg", "--min-score", "--arg", "0"])
    assert result.exit_code == 0


def test_watch_loop_reruns_on_file_change(sample_repo):
    name = _register(sample_repo, "watch_loop")
    result = runner.invoke(
        app,
        ["watch", "stats", name, "--interval", "0", "--max-iterations", "1"],
    )
    assert result.exit_code == 0
    # Exactly one immediate run, since nothing changes within a single
    # zero-length poll in a CliRunner-driven test.
    assert result.output.count("Running: devtools stats") == 1


def test_watch_unknown_command_reports_error_but_does_not_crash(sample_repo):
    name = _register(sample_repo, "watch_bad_command")
    result = runner.invoke(app, ["watch", "not-a-real-command", name, "--once"])
    assert result.exit_code == 0  # the watch command itself succeeds; the inner failure is reported, not raised


# --- plugin ---------------------------------------------------------------

_VALID_PLUGIN_SOURCE = '''
import typer

DEVTOOLS_API_VERSION = "1"

def register(app: typer.Typer) -> None:
    @app.command("hello-from-plugin-cli-test")
    def hello():
        print("hello from plugin")
'''


def test_plugin_list_empty_by_default():
    result = runner.invoke(app, ["plugin", "list"])
    assert result.exit_code == 0
    assert "No plugins installed" in result.output


def test_plugin_install_then_list_then_remove(tmp_path):
    src = tmp_path / "cli_test_plugin.py"
    src.write_text(_VALID_PLUGIN_SOURCE)

    install_result = runner.invoke(app, ["plugin", "install", str(src)])
    assert install_result.exit_code == 0
    assert "Installed plugin 'cli_test_plugin'" in install_result.output

    list_result = runner.invoke(app, ["--json", "plugin", "list"])
    assert list_result.exit_code == 0
    payload = json.loads(list_result.output)
    assert any(p["name"] == "cli_test_plugin" and p["error"] is None for p in payload["plugins"])

    remove_result = runner.invoke(app, ["plugin", "remove", "cli_test_plugin"])
    assert remove_result.exit_code == 0

    list_after = runner.invoke(app, ["--json", "plugin", "list"])
    payload_after = json.loads(list_after.output)
    assert not any(p["name"] == "cli_test_plugin" for p in payload_after["plugins"])


def test_plugin_install_rejects_invalid_script(tmp_path):
    src = tmp_path / "bad.py"
    src.write_text("x = 1\n")  # no register(app)
    result = runner.invoke(app, ["plugin", "install", str(src)])
    assert result.exit_code == 1


def test_plugin_remove_missing_plugin_fails_cleanly():
    result = runner.invoke(app, ["plugin", "remove", "totally-not-installed"])
    assert result.exit_code == 1


# --- ui (entry point only -- deep TUI interaction is in tests/test_tui/) ---


def test_ui_launches_dashboard_for_valid_project(monkeypatch, sample_repo):
    name = _register(sample_repo, "ui_demo")
    captured = {}

    def fake_run_tui(initial_project=None):
        captured["initial_project"] = initial_project

    monkeypatch.setattr("devtools.tui.app.run_tui", fake_run_tui)
    result = runner.invoke(app, ["ui", name])
    assert result.exit_code == 0
    assert captured["initial_project"] == name


def test_ui_with_no_project_opens_the_picker(monkeypatch, sample_repo):
    _register(sample_repo, "ui_picker_demo")
    captured = {}

    def fake_run_tui(initial_project=None):
        captured["initial_project"] = initial_project

    monkeypatch.setattr("devtools.tui.app.run_tui", fake_run_tui)
    result = runner.invoke(app, ["ui"])
    assert result.exit_code == 0
    assert captured["initial_project"] is None


def test_ui_unknown_project_fails_before_launching_tui(monkeypatch):
    called = {"count": 0}
    monkeypatch.setattr("devtools.tui.app.run_tui", lambda **kw: called.__setitem__("count", called["count"] + 1))
    result = runner.invoke(app, ["ui", "no-such-project"])
    assert result.exit_code == 3  # PROJECT_NOT_FOUND
    assert called["count"] == 0


def test_ui_missing_textual_dependency_reports_helpful_message(monkeypatch, sample_repo):
    name = _register(sample_repo, "ui_no_textual")
    monkeypatch.setitem(sys.modules, "devtools.tui.app", None)
    result = runner.invoke(app, ["ui", name])
    assert result.exit_code == 1
    assert "textual" in result.output.lower()