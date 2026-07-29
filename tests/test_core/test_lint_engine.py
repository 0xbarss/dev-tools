from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from devtools.core.lint_engine import (
    ADAPTERS,
    EslintAdapter,
    RuffAdapter,
    detect_ecosystems,
    run_lint,
)


def test_ruff_adapter_detects_python_project(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")
    detected = detect_ecosystems(tmp_path)
    names = [a.name for a in detected]
    assert "ruff" in names


def test_no_ecosystem_detected_for_empty_dir(tmp_path):
    assert detect_ecosystems(tmp_path) == []


@pytest.mark.skipif(shutil.which("ruff") is None, reason="ruff not installed in this environment")
def test_ruff_adapter_real_run_finds_unused_import(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\nversion='0.1'\n")
    (tmp_path / "bad.py").write_text("import os\n\n\ndef f():\n    return 1\n")
    report = run_lint(tmp_path)
    ruff_result = next(r for r in report.results if r.linter == "ruff")
    assert ruff_result.ran is True
    assert any(f.rule == "F401" for f in ruff_result.findings)


def test_eslint_adapter_reports_install_hint_when_missing(tmp_path, monkeypatch):
    (tmp_path / "package.json").write_text("{}")
    monkeypatch.setattr(EslintAdapter, "is_available", lambda self: False)
    report = run_lint(tmp_path)
    eslint_result = next(r for r in report.results if r.linter == "eslint")
    assert eslint_result.ran is False
    assert "eslint" in eslint_result.error


def test_eslint_adapter_parses_json_output(tmp_path, monkeypatch):
    (tmp_path / "package.json").write_text("{}")
    payload = [
        {
            "filePath": str(tmp_path / "app.js"),
            "messages": [
                {"line": 3, "ruleId": "no-unused-vars", "severity": 2, "message": "'x' is defined but never used."}
            ],
        }
    ]

    def fake_run(cmd, cwd):
        return 1, json.dumps(payload), ""

    monkeypatch.setattr(EslintAdapter, "is_available", lambda self: True)
    monkeypatch.setattr("devtools.core.lint_engine._run", fake_run)
    report = run_lint(tmp_path)
    eslint_result = next(r for r in report.results if r.linter == "eslint")
    assert eslint_result.ran is True
    assert eslint_result.findings[0].file == "app.js"
    assert eslint_result.findings[0].severity == "error"
    assert report.has_errors is True


def test_only_ecosystems_filter(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")
    (tmp_path / "package.json").write_text("{}")
    report = run_lint(tmp_path, only_ecosystems=["python"])
    assert {r.ecosystem for r in report.results} == {"python"}


def test_broken_adapter_does_not_abort_whole_run(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")

    def boom(self, root, fix=False):
        raise RuntimeError("boom")

    monkeypatch.setattr(RuffAdapter, "run", boom)
    report = run_lint(tmp_path)
    ruff_result = next(r for r in report.results if r.linter == "ruff")
    assert ruff_result.ran is False
    assert "boom" in ruff_result.error