"""CLI-level tests via Typer's CliRunner (spec §11), asserting exit codes
match the table in spec §5:

    0 success | 1 general error | 2 invalid usage |
    3 project not found | 4 filesystem error | 5 check failed
"""

from __future__ import annotations

import json

from typer.testing import CliRunner

from devtools.cli import app

runner = CliRunner()


def _register(sample_repo, name="demo"):
    result = runner.invoke(app, ["project", "add", name, str(sample_repo)])
    assert result.exit_code == 0, result.output
    return name


def test_init_is_idempotent():
    first = runner.invoke(app, ["init"])
    second = runner.invoke(app, ["init"])
    assert first.exit_code == 0
    assert second.exit_code == 0


def test_project_add_and_list(sample_repo):
    name = _register(sample_repo)
    result = runner.invoke(app, ["project", "list", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    names = {p["name"] for p in payload["projects"]} if isinstance(payload, dict) else {p["name"] for p in payload}
    assert name in names


def test_project_add_rejects_nonexistent_path(tmp_path):
    result = runner.invoke(app, ["project", "add", "ghost", str(tmp_path / "does_not_exist")])
    assert result.exit_code == 2  # invalid usage


def test_unregistered_project_exits_3(sample_repo):
    result = runner.invoke(app, ["stats", "totally-unregistered-project"])
    assert result.exit_code == 3


def test_project_list_fzf_prints_selected_name(sample_repo, monkeypatch):
    name = _register(sample_repo, name="fzf-demo")

    from devtools.commands import project as project_cmd

    monkeypatch.setattr(project_cmd, "run_fzf", lambda lines, **kwargs: [lines[0]])
    result = runner.invoke(app, ["project", "list", "--fzf"])
    assert result.exit_code == 0
    assert result.output.strip() == name


def test_project_list_fzf_falls_back_when_not_installed(sample_repo, monkeypatch):
    _register(sample_repo, name="fzf-demo2")

    from devtools.commands import project as project_cmd

    monkeypatch.setattr(project_cmd, "run_fzf", lambda lines, **kwargs: None)
    result = runner.invoke(app, ["project", "list", "--fzf"])
    assert result.exit_code == 0
    assert "fzf not found on PATH" in result.output


def test_stats_json_output_shape(sample_repo):
    name = _register(sample_repo)
    result = runner.invoke(app, ["--json", "stats", name])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["files"] > 0
    assert "languages" in payload


def test_collect_bad_format_exits_2(sample_repo):
    name = _register(sample_repo)
    result = runner.invoke(app, ["collect", name, "--format", "bogus"])
    assert result.exit_code == 2


def test_collect_ignores_stray_build_and_cache_files(sample_repo):
    # sample_repo already has a node_modules/ dir and a __pycache__/ .pyc
    # file pruned by DEFAULT_IGNORED_DIRS; these are stray build/cache
    # artifacts sitting *outside* any such directory, which only the new
    # ignored_file_patterns layer catches.
    (sample_repo / "src" / "leftover.pyc").write_text("bytecode-ish\n")
    (sample_repo / "src" / "bundle.min.js").write_text("!function(){}();\n")
    (sample_repo / ".DS_Store").write_text("junk\n")

    name = _register(sample_repo, name="collect_ignore_demo")
    result = runner.invoke(app, ["--json", "collect", name])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    paths = {f["path"] for f in payload["files"]}
    assert "src/leftover.pyc" not in paths
    assert "src/bundle.min.js" not in paths
    assert ".DS_Store" not in paths
    assert "src/main.py" in paths


def test_doctor_ci_exits_5_when_issues_found(sample_repo):
    name = _register(sample_repo)
    result = runner.invoke(app, ["doctor", name, "--ci"])
    assert result.exit_code == 5  # sample_repo has no LICENSE, so at least one issue


def test_grep_uses_global_project_flag(sample_repo):
    name = _register(sample_repo)
    result = runner.invoke(app, ["--project", name, "grep", "authenticate", "--json"])
    assert result.exit_code == 0
    matches = json.loads(result.output)
    assert any(m["path"] == "src/auth.py" for m in matches)


def test_tree_respects_ignore_rules(sample_repo):
    name = _register(sample_repo)
    result = runner.invoke(app, ["tree", name])
    assert result.exit_code == 0
    assert "node_modules" not in result.output


def test_history_records_previous_commands(sample_repo):
    name = _register(sample_repo)
    runner.invoke(app, ["stats", name])
    result = runner.invoke(app, ["history", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    entries = payload["history"] if isinstance(payload, dict) else payload
    assert any(e["command"] == "stats" for e in entries)


def test_search_build_index_succeeds_now_implemented(sample_repo):
    name = _register(sample_repo)
    result = runner.invoke(app, ["search", name, "--build-index"])
    assert result.exit_code == 0
    assert "Indexed" in result.output


def test_deps_json_finds_python_manifest(sample_repo):
    name = _register(sample_repo)
    result = runner.invoke(app, ["--json", "deps", name])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert "python" in payload["ecosystems"]
