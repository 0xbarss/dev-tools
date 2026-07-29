from __future__ import annotations

import json

from typer.testing import CliRunner

from devtools.cli import app

runner = CliRunner()


def _register(root, name="demo"):
    result = runner.invoke(app, ["project", "add", name, str(root)])
    assert result.exit_code == 0, result.output
    return name


# --- complexity ---------------------------------------------------------


def test_complexity_reports_functions(sample_repo):
    name = _register(sample_repo, "complexity_demo")
    result = runner.invoke(app, ["complexity", name])
    assert result.exit_code == 0
    assert "complexity" in result.output.lower()


def test_complexity_json_output_shape(sample_repo):
    name = _register(sample_repo, "complexity_json")
    result = runner.invoke(app, ["--json", "complexity", name])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert "functions" in payload
    assert "flagged" in payload
    assert payload["threshold"] == 10


def test_complexity_ci_flag_fails_when_over_threshold(sample_repo):
    name = _register(sample_repo, "complexity_ci")
    result = runner.invoke(app, ["complexity", name, "--threshold", "1", "--ci"])
    assert result.exit_code == 5


def test_complexity_no_functions_reports_cleanly(tmp_path):
    (tmp_path / "README.md").write_text("# empty\n")
    name = _register(tmp_path, "complexity_empty")
    result = runner.invoke(app, ["complexity", name])
    assert result.exit_code == 0
    assert "no python functions" in result.output.lower()


# --- deadcode ------------------------------------------------------------


def test_deadcode_finds_unused_function(tmp_path):
    (tmp_path / "mod.py").write_text("def used():\n    return 1\n\ndef unused():\n    return 2\n\nprint(used())\n")
    name = _register(tmp_path, "deadcode_demo")
    result = runner.invoke(app, ["deadcode", name])
    assert result.exit_code == 0
    assert "unused" in result.output.lower()


def test_deadcode_json_output_shape(sample_repo):
    name = _register(sample_repo, "deadcode_json")
    result = runner.invoke(app, ["--json", "deadcode", name])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert "unused_imports" in payload
    assert "unused_definitions" in payload


def test_deadcode_clean_project_reports_no_issues(tmp_path):
    (tmp_path / "mod.py").write_text("def used():\n    return 1\n\nprint(used())\n")
    name = _register(tmp_path, "deadcode_clean")
    result = runner.invoke(app, ["deadcode", name])
    assert result.exit_code == 0
    assert "no unused" in result.output.lower()


def test_deadcode_ci_flag_fails_when_findings_exist(tmp_path):
    (tmp_path / "mod.py").write_text("def unused():\n    return 1\n")
    name = _register(tmp_path, "deadcode_ci")
    result = runner.invoke(app, ["deadcode", name, "--ci"])
    assert result.exit_code == 5


# --- dupes -----------------------------------------------------------------


def test_dupes_default_mode_finds_exact_file_duplicates(sample_repo):
    (sample_repo / "src" / "copy_of_main.py").write_text((sample_repo / "src" / "main.py").read_text())
    name = _register(sample_repo, "dupes_files")
    result = runner.invoke(app, ["dupes", name])
    assert result.exit_code == 0
    assert "copy_of_main" in result.output


def test_dupes_code_mode_finds_duplicate_blocks(tmp_path):
    block = "def process(items):\n    total = 0\n    for item in items:\n        total += item\n    return total\n"
    (tmp_path / "a.py").write_text(block)
    (tmp_path / "b.py").write_text(block)
    name = _register(tmp_path, "dupes_code")
    result = runner.invoke(app, ["dupes", name, "--code", "--min-lines", "5"])
    assert result.exit_code == 0
    assert "duplicate code" in result.output.lower()


def test_dupes_code_json_output_shape(tmp_path):
    block = "def process(items):\n    total = 0\n    for item in items:\n        total += item\n    return total\n"
    (tmp_path / "a.py").write_text(block)
    (tmp_path / "b.py").write_text(block)
    name = _register(tmp_path, "dupes_code_json")
    result = runner.invoke(app, ["--json", "dupes", name, "--code", "--min-lines", "5"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert "duplicate_blocks" in payload
    assert payload["min_lines"] == 5


def test_dupes_ci_flag_fails_on_duplicates(sample_repo):
    (sample_repo / "src" / "copy_of_main.py").write_text((sample_repo / "src" / "main.py").read_text())
    name = _register(sample_repo, "dupes_ci")
    result = runner.invoke(app, ["dupes", name, "--ci"])
    assert result.exit_code == 5


def test_dupes_no_duplicates_reports_cleanly(tmp_path):
    (tmp_path / "a.py").write_text("def add(a, b):\n    return a + b\n")
    name = _register(tmp_path, "dupes_none")
    result = runner.invoke(app, ["dupes", name])
    assert result.exit_code == 0
    assert "no duplicate files" in result.output.lower()