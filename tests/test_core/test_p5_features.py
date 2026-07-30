"""Core-engine tests for the backlog items implemented in this pass:
commit-lint (#18), contributors (#16), pr describe (#19), commit explain
(#26), review --security (#28), snapshot (#32), new/scaffold (#33),
run/task-runner (#40), sonar-import/SARIF (#46), daemon (#51).
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

import pytest


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
    _git(root, "commit", "-q", "-m", "feat: initial commit")
    (root / "a.py").write_text("def f():\n    return 2\n")
    (root / "b.py").write_text("def g():\n    return 3\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "fix(core): handle edge case")
    return root


class FakeClient:
    def __init__(self, response):
        self._response = response

    def complete(self, prompt, system=None):
        self.last_prompt = prompt
        return self._response


# --- commit-lint (#18) -------------------------------------------------------


def test_lint_subject_accepts_conventional_commits():
    from devtools.core.commit_lint_engine import lint_subject

    assert lint_subject("feat(auth): add login flow") == []
    assert lint_subject("fix: handle null pointer") == []


def test_lint_subject_flags_non_conventional():
    from devtools.core.commit_lint_engine import lint_subject

    reasons = lint_subject("did stuff")
    assert reasons and "known types" in reasons[0]


def test_lint_subject_flags_unknown_type_and_style_issues():
    from devtools.core.commit_lint_engine import lint_subject

    reasons = lint_subject("bogus: Fixed the thing.")
    assert any("unknown type" in r for r in reasons)
    assert any("lowercase" in r for r in reasons)
    assert any("period" in r for r in reasons)


def test_lint_subject_exempts_merge_commits():
    from devtools.core.commit_lint_engine import lint_subject

    assert lint_subject("Merge branch 'main' into feature") == []


def test_lint_range_over_git_repo(git_repo):
    from devtools.core.commit_lint_engine import lint_range

    report = lint_range(git_repo)
    assert report.ok
    assert report.commits_scanned == 2


# --- contributors (#16) ------------------------------------------------------


def test_compute_contributors_aggregates_by_author(git_repo):
    from devtools.core.contributors_engine import compute_contributors

    report = compute_contributors(git_repo)
    assert len(report.contributors) == 1
    c = report.contributors[0]
    assert c.commits == 2
    assert c.additions >= 3  # a.py x2 (1 line each) + b.py (1 line)


# --- pr describe (#19) -------------------------------------------------------


def test_describe_pr_groups_by_conventional_type(git_repo):
    from devtools.core.pr_engine import describe_pr, render_pr_description_markdown

    first_commit = subprocess.run(
        ["git", "rev-list", "--max-parents=0", "HEAD"], cwd=git_repo, check=True, capture_output=True, text=True
    ).stdout.strip()
    desc = describe_pr(git_repo, since=first_commit)
    assert len(desc.files_changed) == 2
    assert any("Fixed" in b or "fix" in b.lower() for b in desc.summary_bullets)
    md = render_pr_description_markdown(desc)
    assert "## Summary" in md
    assert "## Changes" in md


# --- commit explain (#26) ----------------------------------------------------


def test_explain_commit_uses_llm_client(git_repo):
    from devtools.core.commit_engine import explain_commit

    client = FakeClient("This commit fixes an edge case in f().")
    explanation = explain_commit(git_repo, "HEAD", client)
    assert explanation == "This commit fixes an edge case in f()."
    assert "fix(core): handle edge case" in client.last_prompt


# --- review --security (#28) -------------------------------------------------


def test_scan_diff_flags_hardcoded_secret_and_eval(tmp_path):
    from devtools.core.security_engine import scan_diff

    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "a@b.com")
    _git(root, "config", "user.name", "Test")
    (root / "app.py").write_text("x = 1\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "feat: init")
    (root / "app.py").write_text('x = 1\napi_key = "sk-abcdefgh12345678"\nresult = eval(user_input)\n')
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "feat: add config")

    findings = scan_diff(root, "HEAD~1")
    rules = {f.rule for f in findings}
    assert "hardcoded-secret" in rules
    assert "python-eval-exec" in rules


def test_scan_diff_ignores_removed_lines(tmp_path):
    from devtools.core.security_engine import scan_diff

    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "a@b.com")
    _git(root, "config", "user.name", "Test")
    (root / "app.py").write_text('api_key = "sk-abcdefgh12345678"\n')
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "feat: init")
    (root / "app.py").write_text("x = 1\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "fix: remove secret")

    findings = scan_diff(root, "HEAD~1")
    assert findings == []


# --- snapshot (#32) -----------------------------------------------------------


def test_snapshot_save_load_remove_roundtrip(tmp_path):
    from devtools.core.snapshot_store import load_snapshots, remove_snapshot, save_snapshot

    path = tmp_path / "snapshots.json"
    save_snapshot("wip", project="demo", branch="feature-x", files=["a.py", "b.py"], note="mid-refactor", path=path)

    snapshots = load_snapshots(path)
    assert "wip" in snapshots
    assert snapshots["wip"].branch == "feature-x"
    assert snapshots["wip"].files == ["a.py", "b.py"]

    assert remove_snapshot("wip", path) is True
    assert load_snapshots(path) == {}
    assert remove_snapshot("wip", path) is False


# --- new / scaffold (#33) -----------------------------------------------------


def test_scaffold_python_cli_creates_expected_files(tmp_path):
    from devtools.core.scaffold_engine import scaffold

    target = tmp_path / "my-tool"
    created = scaffold("python-cli", target, "my-tool")
    assert (target / "pyproject.toml").is_file()
    assert (target / "src" / "my_tool" / "cli.py").is_file()
    assert (target / "LICENSE").is_file()
    assert "README.md" in created


def test_scaffold_refuses_nonempty_target(tmp_path):
    from devtools.core.scaffold_engine import scaffold

    target = tmp_path / "existing"
    target.mkdir()
    (target / "file.txt").write_text("hi")
    with pytest.raises(FileExistsError):
        scaffold("python-lib", target, "existing")


def test_scaffold_unknown_template_raises(tmp_path):
    from devtools.core.scaffold_engine import scaffold

    with pytest.raises(ValueError):
        scaffold("rust-cli", tmp_path / "x", "x")


# --- run / task-runner (#40) --------------------------------------------------


def test_discover_tasks_finds_makefile_and_npm_targets(tmp_path):
    from devtools.core.task_runner_engine import discover_tasks

    (tmp_path / "Makefile").write_text("test:\n\tpytest\n\nbuild: test\n\techo building\n\n.PHONY: test build\n")
    (tmp_path / "package.json").write_text(json.dumps({"scripts": {"lint": "eslint ."}}))

    tasks = discover_tasks(tmp_path)
    names = {(t.name, t.source) for t in tasks}
    assert ("test", "make") in names
    assert ("build", "make") in names
    assert ("lint", "npm") in names
    assert not any(t.name == "PHONY" for t in tasks)


def test_run_task_executes_and_returns_exit_code(tmp_path):
    from devtools.core.task_runner_engine import find_task, run_task

    (tmp_path / "Makefile").write_text("ok:\n\ttrue\n\nfail:\n\tfalse\n")
    ok_task = find_task(tmp_path, "ok")[0]
    assert run_task(tmp_path, ok_task) == 0
    fail_task = find_task(tmp_path, "fail")[0]
    assert run_task(tmp_path, fail_task) != 0


# --- sonar-import / SARIF (#46) ----------------------------------------------


def test_load_external_report_parses_sarif(tmp_path):
    from devtools.core.sarif_import import load_external_report

    sarif = {
        "version": "2.1.0",
        "runs": [
            {
                "tool": {"driver": {"name": "CodeQL"}},
                "results": [
                    {
                        "ruleId": "py/sql-injection",
                        "level": "error",
                        "message": {"text": "Possible SQL injection"},
                        "locations": [{"physicalLocation": {"artifactLocation": {"uri": "db.py"}, "region": {"startLine": 10}}}],
                    }
                ],
            }
        ],
    }
    path = tmp_path / "report.sarif"
    path.write_text(json.dumps(sarif))

    report = load_external_report(path)
    assert report.tools == ["CodeQL"]
    assert report.error_count == 1
    assert report.findings[0].file == "db.py"
    assert report.findings[0].line == 10


def test_load_external_report_parses_generic_shape(tmp_path):
    from devtools.core.sarif_import import load_external_report

    generic = {"tool": "custom-scanner", "issues": [{"severity": "warning", "message": "TODO left in code", "file": "x.py", "line": 5}]}
    path = tmp_path / "report.json"
    path.write_text(json.dumps(generic))

    report = load_external_report(path)
    assert report.warning_count == 1
    assert report.findings[0].tool == "custom-scanner"


def test_load_external_report_rejects_unrecognized_shape(tmp_path):
    from devtools.core.sarif_import import ExternalReportError, load_external_report

    path = tmp_path / "report.json"
    path.write_text(json.dumps({"foo": "bar"}))
    with pytest.raises(ExternalReportError):
        load_external_report(path)


def test_health_folds_in_external_report(git_repo):
    from devtools.core.health_engine import compute_health
    from devtools.core.ignore_rules import IgnoreRules
    from devtools.core.sarif_import import ExternalFinding, ExternalScanReport

    rules = IgnoreRules.build(root=git_repo, base_ignored_dirs=[])
    external = ExternalScanReport(
        source_path="x.json",
        tools=["Semgrep"],
        findings=[ExternalFinding(tool="Semgrep", rule="r1", severity="error", file="a.py", line=1, message="bad")],
    )
    report = compute_health(git_repo, rules, [], external_report=external)
    names = [c.name for c in report.categories]
    assert "external" in names
    assert report.overall_score <= 100


# --- daemon (#51) --------------------------------------------------------------


def test_daemon_start_status_stop_lifecycle(tmp_path, monkeypatch):
    from devtools.core import daemon_engine

    monkeypatch.setenv("DEVTOOLS_DAEMON_DIR", str(tmp_path / "daemon"))

    result = daemon_engine.start("proj", tmp_path, "true", interval=100)
    assert result.running
    assert result.pid is not None

    status = daemon_engine.status("proj")
    assert status.running

    with pytest.raises(daemon_engine.DaemonError):
        daemon_engine.start("proj", tmp_path, "true", interval=100)

    stopped = daemon_engine.stop("proj")
    assert stopped is True

    # give the OS a moment to actually reap the process before re-checking
    time.sleep(0.2)
    assert not daemon_engine.status("proj").running


def test_daemon_stop_when_nothing_running_returns_false(tmp_path, monkeypatch):
    from devtools.core import daemon_engine

    monkeypatch.setenv("DEVTOOLS_DAEMON_DIR", str(tmp_path / "daemon"))
    assert daemon_engine.stop("nonexistent") is False
