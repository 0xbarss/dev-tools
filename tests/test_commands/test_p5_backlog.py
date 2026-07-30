"""CLI-level tests for the backlog items implemented in this pass:
commit-lint (#18), contributors (#16), pr describe (#19), docs generate
(#23), commit explain (#26), review --security (#28), snapshot (#32),
new/scaffold (#33), run (#40), sonar-import (#46), daemon (#51).
"""

from __future__ import annotations

import json
import subprocess

from typer.testing import CliRunner

from devtools.cli import app

runner = CliRunner()


def _git(root, *args):
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def _register(root, name="demo"):
    result = runner.invoke(app, ["project", "add", name, str(root)])
    assert result.exit_code == 0, result.output
    return name


def _git_repo(tmp_path, name="repo"):
    root = tmp_path / name
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "a@b.com")
    _git(root, "config", "user.name", "Test")
    (root / "a.py").write_text("print(1)\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "feat: initial commit")
    (root / "a.py").write_text("print(2)\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "not conventional")
    return root


# --- commit-lint (#18) --------------------------------------------------------


def test_commit_lint_cli_reports_violation_and_ci_flag(tmp_path):
    root = _git_repo(tmp_path)
    name = _register(root, "cl_demo")

    result = runner.invoke(app, ["--json", "commit-lint", name, "--since", ""])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["ok"] is False
    assert any("not conventional" in v["subject"] for v in payload["violations"])

    result = runner.invoke(app, ["commit-lint", name, "--since", "", "--ci"])
    assert result.exit_code == 5


def test_commit_lint_range_flag_splits_on_dotdot(tmp_path):
    root = _git_repo(tmp_path)
    name = _register(root, "cl_range_demo")
    result = runner.invoke(app, ["commit-lint", name, "--range", "not-a-range"])
    assert result.exit_code != 0


# --- contributors (#16) -------------------------------------------------------


def test_contributors_cli_lists_author(tmp_path):
    root = _git_repo(tmp_path)
    name = _register(root, "contrib_demo")
    result = runner.invoke(app, ["--json", "contributors", name])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["contributors"][0]["author_name"] == "Test"
    assert payload["contributors"][0]["commits"] == 2


# --- pr describe (#19) --------------------------------------------------------


def test_pr_describe_cli_renders_markdown(tmp_path):
    root = _git_repo(tmp_path)
    name = _register(root, "pr_describe_demo")
    first = subprocess.run(["git", "rev-list", "--max-parents=0", "HEAD"], cwd=root, check=True, capture_output=True, text=True).stdout.strip()
    result = runner.invoke(app, ["pr", "describe", name, "--since", first])
    assert result.exit_code == 0
    assert "## Summary" in result.output
    assert "## Changes" in result.output


# --- docs generate (#23) ------------------------------------------------------


def test_docs_generate_falls_back_to_stub_without_ai(tmp_path):
    root = tmp_path / "docsproj"
    root.mkdir()
    name = _register(root, "docs_demo")
    result = runner.invoke(app, ["docs", "generate", name])
    assert result.exit_code == 0
    assert "docs_demo" in result.output or "TODO" in result.output


def test_docs_generate_write_refuses_existing_without_force(tmp_path):
    root = tmp_path / "docsproj2"
    root.mkdir()
    (root / "README.md").write_text("# already here\n")
    name = _register(root, "docs_demo2")
    result = runner.invoke(app, ["docs", "generate", name, "--write"])
    assert result.exit_code != 0

    result = runner.invoke(app, ["docs", "generate", name, "--write", "--force"])
    assert result.exit_code == 0
    assert (root / "README.md").is_file()


# --- commit explain (#26) -----------------------------------------------------


def test_commit_explain_cli_fails_gracefully_without_ai(tmp_path):
    root = _git_repo(tmp_path)
    name = _register(root, "commit_explain_demo")
    result = runner.invoke(app, ["commit", "explain", name, "HEAD"])
    assert result.exit_code != 0
    assert "No AI provider configured" in result.output


# --- review --security (#28) --------------------------------------------------


def test_review_security_flag_reports_pattern_findings(tmp_path):
    root = tmp_path / "secrepo"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "a@b.com")
    _git(root, "config", "user.name", "Test")
    (root / "app.py").write_text("x = 1\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "feat: init")
    (root / "app.py").write_text('x = 1\napi_key = "sk-abcdefgh12345678"\n')
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "feat: add key")
    name = _register(root, "sec_demo")

    result = runner.invoke(app, ["review", name, "--security", "--since", "HEAD~1"])
    assert result.exit_code == 0
    assert "hardcoded-secret" in result.output


# --- snapshot (#32) -----------------------------------------------------------


def test_snapshot_cli_save_list_restore_remove(tmp_path):
    root = _git_repo(tmp_path)
    name = _register(root, "snap_demo")

    result = runner.invoke(app, ["snapshot", "save", "wip1", "--project", name, "--file", "a.py", "--note", "note here"])
    assert result.exit_code == 0

    result = runner.invoke(app, ["--json", "snapshot", "list"])
    payload = json.loads(result.output)["snapshots"]
    assert any(s["name"] == "wip1" for s in payload)

    result = runner.invoke(app, ["snapshot", "restore", "wip1"])
    assert result.exit_code == 0
    assert "note here" in result.output

    result = runner.invoke(app, ["snapshot", "remove", "wip1"])
    assert result.exit_code == 0
    result = runner.invoke(app, ["snapshot", "restore", "wip1"])
    assert result.exit_code != 0


# --- new / scaffold (#33) -----------------------------------------------------


def test_new_cli_scaffolds_and_registers(tmp_path):
    target = tmp_path / "scaffolded"
    result = runner.invoke(app, ["new", "python-lib", "scaffolded-lib", "--path", str(target), "--no-license"])
    assert result.exit_code == 0, result.output
    assert (target / "pyproject.toml").is_file()
    assert not (target / "LICENSE").exists()

    result = runner.invoke(app, ["--json", "project", "list"])
    payload = json.loads(result.output)
    assert any(p["name"] == "scaffolded-lib" for p in payload["projects"])


def test_new_cli_unknown_template_fails(tmp_path):
    result = runner.invoke(app, ["new", "cobol-cli", "x", "--path", str(tmp_path / "x")])
    assert result.exit_code != 0
    assert "Unknown template" in result.output


# --- run (#40) -----------------------------------------------------------------


def test_run_cli_list_and_execute(tmp_path):
    root = tmp_path / "runproj"
    root.mkdir()
    (root / "Makefile").write_text("hello:\n\techo hi\n")
    name = _register(root, "run_demo")

    result = runner.invoke(app, ["--json", "run", name, "--list"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert any(t["name"] == "hello" for t in payload["tasks"])

    result = runner.invoke(app, ["run", name, "hello"])
    assert result.exit_code == 0


def test_run_cli_unknown_task_fails(tmp_path):
    root = tmp_path / "runproj2"
    root.mkdir()
    name = _register(root, "run_demo2")
    result = runner.invoke(app, ["run", name, "does-not-exist"])
    assert result.exit_code != 0


# --- sonar-import / health --external-report (#46) ----------------------------


def test_sonar_import_and_health_external_report_cli(tmp_path):
    root = _git_repo(tmp_path)
    name = _register(root, "sonar_demo")

    sarif = {
        "version": "2.1.0",
        "runs": [
            {
                "tool": {"driver": {"name": "Semgrep"}},
                "results": [{"ruleId": "r1", "level": "error", "message": {"text": "bad"}, "locations": [{"physicalLocation": {"artifactLocation": {"uri": "a.py"}, "region": {"startLine": 1}}}]}],
            }
        ],
    }
    report_path = tmp_path / "report.sarif"
    report_path.write_text(json.dumps(sarif))

    result = runner.invoke(app, ["--json", "sonar-import", str(report_path), name])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["error_count"] == 1

    result = runner.invoke(app, ["--json", "health", name, "--external-report", str(report_path)])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert any(c["name"] == "external" for c in payload["categories"])


def test_sonar_import_rejects_bad_file(tmp_path):
    root = _git_repo(tmp_path)
    name = _register(root, "sonar_bad_demo")
    bad_path = tmp_path / "bad.json"
    bad_path.write_text("{}")
    result = runner.invoke(app, ["sonar-import", str(bad_path), name])
    assert result.exit_code != 0


# --- daemon (#51) ---------------------------------------------------------------


def test_daemon_cli_start_status_stop(tmp_path, monkeypatch):
    monkeypatch.setenv("DEVTOOLS_DAEMON_DIR", str(tmp_path / "daemondir"))
    root = _git_repo(tmp_path, "daemonproj")
    name = _register(root, "daemon_demo")

    result = runner.invoke(app, ["daemon", "start", "stats", name, "--interval", "60"])
    assert result.exit_code == 0, result.output

    result = runner.invoke(app, ["--json", "daemon", "status", name])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["running"] is True

    result = runner.invoke(app, ["daemon", "stop", name])
    assert result.exit_code == 0


def test_daemon_cli_stop_when_not_running_fails(tmp_path, monkeypatch):
    monkeypatch.setenv("DEVTOOLS_DAEMON_DIR", str(tmp_path / "daemondir2"))
    root = _git_repo(tmp_path, "daemonproj2")
    name = _register(root, "daemon_demo2")
    result = runner.invoke(app, ["daemon", "stop", name])
    assert result.exit_code != 0
