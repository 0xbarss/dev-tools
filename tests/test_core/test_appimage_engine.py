from __future__ import annotations

from pathlib import Path

import pytest

from devtools.core import appimage_engine


def _fake_extract_factory(squashfs_contents):
    """Build a fake `subprocess.run` that, instead of really running
    `--appimage-extract`, materializes `squashfs_contents` (a dict of
    relative-path -> text/bytes) under <cwd>/squashfs-root."""

    def _fake_run(cmd, cwd=None, capture_output=None, text=None):
        appdir = Path(cwd) / "squashfs-root"
        appdir.mkdir(parents=True, exist_ok=True)
        for rel_path, content in squashfs_contents.items():
            target = appdir / rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, bytes):
                target.write_bytes(content)
            else:
                target.write_text(content)

        class FakeResult:
            returncode = 0
            stdout = ""
            stderr = ""

        return FakeResult()

    return _fake_run


@pytest.fixture
def fake_appimage(tmp_path):
    path = tmp_path / "MyApp.AppImage"
    path.write_text("not a real appimage, just a placeholder\n")
    path.chmod(0o755)
    return path


def test_install_reuses_bundled_desktop_entry(monkeypatch, tmp_path, fake_appimage):
    bundled = (
        "[Desktop Entry]\n"
        "Name=My App\n"
        "Comment=Does things\n"
        "Exec=AppRun %U\n"
        "Icon=myapp\n"
        "Path=/tmp/some/extraction/dir\n"
        "Type=Application\n"
        "Categories=Utility;\n"
    )
    fake_run = _fake_extract_factory({"MyApp.desktop": bundled, "myapp.png": b"\x89PNG..."})
    monkeypatch.setattr(appimage_engine.subprocess, "run", fake_run)

    apps_dir = tmp_path / "applications"
    icons_dir = tmp_path / "icons"

    result = appimage_engine.install_shortcut(fake_appimage, applications_dir=apps_dir, icons_dir=icons_dir)

    assert result.source == "bundled"
    text = result.desktop_entry_path.read_text()
    assert f'Exec="{fake_appimage.resolve()}"' in text
    assert f"Icon={icons_dir / 'MyApp.png'}" in text
    # The bundled Name/Comment/Categories should be preserved verbatim.
    assert "Name=My App" in text
    assert "Comment=Does things" in text
    assert "Categories=Utility;" in text
    # The extraction-dir-only Path= must not survive into the installed entry.
    assert "Path=" not in text
    assert result.icon_path.is_file()


def test_install_generates_entry_when_no_bundled_desktop(monkeypatch, tmp_path, fake_appimage):
    fake_run = _fake_extract_factory({"icon.png": b"\x89PNG..."})
    monkeypatch.setattr(appimage_engine.subprocess, "run", fake_run)

    apps_dir = tmp_path / "applications"
    icons_dir = tmp_path / "icons"

    result = appimage_engine.install_shortcut(fake_appimage, applications_dir=apps_dir, icons_dir=icons_dir)

    assert result.source == "generated"
    text = result.desktop_entry_path.read_text()
    assert "Name=MyApp" in text
    assert f'Exec="{fake_appimage.resolve()}"' in text


def test_install_raises_on_ambiguous_icons_without_choice(monkeypatch, tmp_path, fake_appimage):
    fake_run = _fake_extract_factory({"a.png": b"1", "b.svg": b"2"})
    monkeypatch.setattr(appimage_engine.subprocess, "run", fake_run)

    with pytest.raises(appimage_engine.AppImageError, match="Multiple icons"):
        appimage_engine.install_shortcut(
            fake_appimage, applications_dir=tmp_path / "applications", icons_dir=tmp_path / "icons"
        )


def test_install_accepts_icon_choice_by_index(monkeypatch, tmp_path, fake_appimage):
    fake_run = _fake_extract_factory({"a.png": b"1", "b.svg": b"2"})
    monkeypatch.setattr(appimage_engine.subprocess, "run", fake_run)

    result = appimage_engine.install_shortcut(
        fake_appimage,
        icon_choice="2",
        applications_dir=tmp_path / "applications",
        icons_dir=tmp_path / "icons",
    )
    assert result.icon_path.suffix == ".svg"


def test_install_raises_when_no_icons_found(monkeypatch, tmp_path, fake_appimage):
    fake_run = _fake_extract_factory({})
    monkeypatch.setattr(appimage_engine.subprocess, "run", fake_run)

    with pytest.raises(appimage_engine.AppImageError, match="No .png or .svg icon"):
        appimage_engine.install_shortcut(
            fake_appimage, applications_dir=tmp_path / "applications", icons_dir=tmp_path / "icons"
        )


def test_install_raises_when_extraction_fails(monkeypatch, tmp_path, fake_appimage):
    def _failing_run(cmd, cwd=None, capture_output=None, text=None):
        class FakeResult:
            returncode = 1
            stdout = ""
            stderr = "not an AppImage"

        return FakeResult()

    monkeypatch.setattr(appimage_engine.subprocess, "run", _failing_run)

    with pytest.raises(appimage_engine.AppImageError, match="Failed to extract"):
        appimage_engine.install_shortcut(
            fake_appimage, applications_dir=tmp_path / "applications", icons_dir=tmp_path / "icons"
        )


def test_install_missing_file_raises(tmp_path):
    with pytest.raises(appimage_engine.AppImageError, match="File not found"):
        appimage_engine.install_shortcut(
            tmp_path / "nope.AppImage", applications_dir=tmp_path / "applications", icons_dir=tmp_path / "icons"
        )


def test_remove_shortcut_removes_entry_and_icon(tmp_path):
    apps_dir = tmp_path / "applications"
    icons_dir = tmp_path / "icons"
    apps_dir.mkdir()
    icons_dir.mkdir()
    (apps_dir / "MyApp.desktop").write_text("[Desktop Entry]\n")
    (icons_dir / "MyApp.png").write_bytes(b"1")

    removed = appimage_engine.remove_shortcut("MyApp", applications_dir=apps_dir, icons_dir=icons_dir)
    assert removed is True
    assert not (apps_dir / "MyApp.desktop").exists()
    assert not (icons_dir / "MyApp.png").exists()


def test_remove_shortcut_no_op_when_nothing_installed(tmp_path):
    removed = appimage_engine.remove_shortcut(
        "NoSuchApp", applications_dir=tmp_path / "applications", icons_dir=tmp_path / "icons"
    )
    assert removed is False


def test_adapt_bundled_desktop_entry_leaves_action_groups_alone():
    bundled = (
        "[Desktop Entry]\n"
        "Name=My App\n"
        "Exec=AppRun %U\n"
        "Icon=myapp\n"
        "Actions=NewWindow;\n"
        "\n"
        "[Desktop Action NewWindow]\n"
        "Name=New Window\n"
        "Exec=AppRun --new-window\n"
    )
    out = appimage_engine.adapt_bundled_desktop_entry(bundled, Path("/opt/MyApp.AppImage"), Path("/home/u/.local/share/icons/MyApp.png"))
    assert 'Exec="/opt/MyApp.AppImage"' in out
    # The action group's own Exec is untouched (it can't be fixed here).
    assert "Exec=AppRun --new-window" in out


def test_resolve_icon_choice_by_filename(tmp_path):
    a = tmp_path / "a.png"
    b = tmp_path / "b.svg"
    a.write_text("")
    b.write_text("")
    assert appimage_engine.resolve_icon_choice([a, b], "b.svg") == b


def test_resolve_icon_choice_out_of_range(tmp_path):
    a = tmp_path / "a.png"
    a.write_text("")
    with pytest.raises(appimage_engine.AppImageError, match="out of range"):
        appimage_engine.resolve_icon_choice([a], "5")
