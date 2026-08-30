from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from devtools.cli import app
from devtools.core import appimage_engine

runner = CliRunner()


def _fake_extract_factory(squashfs_contents):
    def _fake_run(cmd, cwd=None, capture_output=None, text=None):
        appdir = Path(cwd) / "squashfs-root"
        appdir.mkdir(parents=True, exist_ok=True)
        for rel_path, content in squashfs_contents.items():
            target = appdir / rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content if isinstance(content, bytes) else content.encode())

        class FakeResult:
            returncode = 0
            stdout = ""
            stderr = ""

        return FakeResult()

    return _fake_run


def test_appimage_install_missing_file_fails(tmp_path, monkeypatch):
    monkeypatch.setenv("DEVTOOLS_APPLICATIONS_DIR", str(tmp_path / "applications"))
    monkeypatch.setenv("DEVTOOLS_ICONS_DIR", str(tmp_path / "icons"))
    result = runner.invoke(app, ["appimage", "install", str(tmp_path / "nope.AppImage")])
    assert result.exit_code != 0
    assert "File not found" in result.output


def test_appimage_install_and_remove_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("DEVTOOLS_APPLICATIONS_DIR", str(tmp_path / "applications"))
    monkeypatch.setenv("DEVTOOLS_ICONS_DIR", str(tmp_path / "icons"))
    monkeypatch.setattr(
        appimage_engine.subprocess,
        "run",
        _fake_extract_factory({"MyApp.desktop": "[Desktop Entry]\nName=My App\nExec=AppRun\nIcon=myapp\n", "myapp.png": b"1"}),
    )

    appimage_path = tmp_path / "MyApp.AppImage"
    appimage_path.write_text("placeholder")

    result = runner.invoke(app, ["--json", "appimage", "install", str(appimage_path)])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["source"] == "bundled"
    assert Path(payload["desktop_entry_path"]).is_file()

    result = runner.invoke(app, ["--json", "appimage", "remove", payload["app_name"]])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["removed"] is True
    assert not Path(payload["desktop_entry_path"]).exists()


def test_appimage_install_list_icons(tmp_path, monkeypatch):
    monkeypatch.setattr(appimage_engine.subprocess, "run", _fake_extract_factory({"a.png": b"1", "b.svg": b"2"}))
    appimage_path = tmp_path / "MyApp.AppImage"
    appimage_path.write_text("placeholder")

    result = runner.invoke(app, ["--json", "appimage", "install", str(appimage_path), "--list-icons"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert sorted(payload["icons"]) == ["a.png", "b.svg"]


def test_appimage_install_ambiguous_icons_fails_cleanly(tmp_path, monkeypatch):
    monkeypatch.setenv("DEVTOOLS_APPLICATIONS_DIR", str(tmp_path / "applications"))
    monkeypatch.setenv("DEVTOOLS_ICONS_DIR", str(tmp_path / "icons"))
    monkeypatch.setattr(appimage_engine.subprocess, "run", _fake_extract_factory({"a.png": b"1", "b.svg": b"2"}))
    appimage_path = tmp_path / "MyApp.AppImage"
    appimage_path.write_text("placeholder")

    result = runner.invoke(app, ["appimage", "install", str(appimage_path)])
    assert result.exit_code != 0
    assert "Multiple icons" in result.output


def test_appimage_remove_nothing_installed(tmp_path, monkeypatch):
    monkeypatch.setenv("DEVTOOLS_APPLICATIONS_DIR", str(tmp_path / "applications"))
    monkeypatch.setenv("DEVTOOLS_ICONS_DIR", str(tmp_path / "icons"))
    result = runner.invoke(app, ["appimage", "remove", "NoSuchApp"])
    assert result.exit_code == 0
    assert "Nothing to remove" in result.output
