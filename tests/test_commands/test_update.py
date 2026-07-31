from __future__ import annotations

import json

from typer.testing import CliRunner

from devtools.cli import app

runner = CliRunner()


def _write_pyproject(path, version="9.9.9"):
    path.mkdir(parents=True, exist_ok=True)
    (path / "pyproject.toml").write_text(f'[project]\nname = "devtools"\nversion = "{version}"\n')


def test_update_check_reports_source_version(tmp_path):
    source = tmp_path / "checkout"
    _write_pyproject(source, version="9.9.9")

    result = runner.invoke(app, ["update", "--check", "--source", str(source)])
    assert result.exit_code == 0
    assert "9.9.9" in result.output


def test_update_check_json_shape(tmp_path):
    source = tmp_path / "checkout"
    _write_pyproject(source, version="9.9.9")

    result = runner.invoke(app, ["--json", "update", "--check", "--source", str(source)])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["source_version"] == "9.9.9"
    assert payload["source_path"] == str(source)
    assert payload["up_to_date"] is False


def test_update_missing_pyproject_fails_cleanly(tmp_path):
    result = runner.invoke(app, ["update", "--check", "--source", str(tmp_path / "nope")])
    assert result.exit_code == 2
    assert "No pyproject.toml found" in result.output


def test_update_requires_allow_network(tmp_path):
    source = tmp_path / "checkout"
    _write_pyproject(source)
    result = runner.invoke(app, ["update", "--source", str(source)])
    assert result.exit_code == 2
    assert "allow_network" in result.output


def test_update_fails_cleanly_when_uv_not_on_path(tmp_path, monkeypatch):
    source = tmp_path / "checkout"
    _write_pyproject(source)
    runner.invoke(app, ["config", "set", "allow_network", "true"])

    from devtools.commands import update as update_cmd

    monkeypatch.setattr(update_cmd.shutil, "which", lambda name: None)
    result = runner.invoke(app, ["update", "--source", str(source)])
    assert result.exit_code == 1
    assert "uv" in result.output
    assert "not found on PATH" in result.output


def test_update_runs_uv_tool_install_with_extras(tmp_path, monkeypatch):
    source = tmp_path / "checkout"
    _write_pyproject(source)
    runner.invoke(app, ["config", "set", "allow_network", "true"])

    from devtools.commands import update as update_cmd

    monkeypatch.setattr(update_cmd.shutil, "which", lambda name: "/usr/bin/uv")

    captured = {}

    class FakeResult:
        returncode = 0

    def fake_run(cmd):
        captured["cmd"] = cmd
        return FakeResult()

    monkeypatch.setattr(update_cmd.subprocess, "run", fake_run)

    result = runner.invoke(app, ["update", "--source", str(source)])
    assert result.exit_code == 0
    assert captured["cmd"][:3] == ["uv", "tool", "install"]
    assert captured["cmd"][3] == f"{source}[dev,tui,mcp]"
    assert "Reinstalled devtools" in result.output


def test_update_reports_uv_tool_install_failure(tmp_path, monkeypatch):
    source = tmp_path / "checkout"
    _write_pyproject(source)
    runner.invoke(app, ["config", "set", "allow_network", "true"])

    from devtools.commands import update as update_cmd

    monkeypatch.setattr(update_cmd.shutil, "which", lambda name: "/usr/bin/uv")

    class FakeResult:
        returncode = 1

    monkeypatch.setattr(update_cmd.subprocess, "run", lambda cmd: FakeResult())

    result = runner.invoke(app, ["update", "--source", str(source)])
    assert result.exit_code == 1
    assert "failed" in result.output


def test_update_respects_configured_extras(tmp_path, monkeypatch):
    source = tmp_path / "checkout"
    _write_pyproject(source)
    runner.invoke(app, ["config", "set", "allow_network", "true"])
    runner.invoke(app, ["config", "set", "update_extras", "dev"])

    from devtools.commands import update as update_cmd

    monkeypatch.setattr(update_cmd.shutil, "which", lambda name: "/usr/bin/uv")

    captured = {}

    class FakeResult:
        returncode = 0

    def fake_run(cmd):
        captured["cmd"] = cmd
        return FakeResult()

    monkeypatch.setattr(update_cmd.subprocess, "run", fake_run)

    result = runner.invoke(app, ["update", "--source", str(source)])
    assert result.exit_code == 0
    assert captured["cmd"][3] == f"{source}[dev]"


def test_update_uses_configured_source_path_by_default(tmp_path):
    source = tmp_path / "default_checkout"
    _write_pyproject(source, version="1.2.3")
    runner.invoke(app, ["config", "set", "update_source_path", str(source)])

    result = runner.invoke(app, ["update", "--check"])
    assert result.exit_code == 0
    assert "1.2.3" in result.output
