"""`devtools appimage` -- install a `.desktop` launcher + icon for an
AppImage (backlog: desktop integration, replaces the old standalone
`script.sh`).

Per the AppImage spec, a well-formed AppDir ships exactly one `.desktop`
file at its root, already carrying the correct Name/Comment/Categories/
MimeType/etc. We prefer reusing that over generating one from scratch --
only rewriting the handful of keys that must point at *our* install (the
AppImage file itself + the icon we copy out) rather than at the throwaway
extraction directory, which is deleted before the function returns. In
particular, a bundled entry's `Exec=`/`TryExec=`/`Icon=`/`Path=` all
reference paths inside that extraction dir and would otherwise silently
break the moment cleanup runs.

Only the `[Desktop Entry]` group is rewritten -- a bundled file's
`[Desktop Action ...]` groups (e.g. "New Window") reference the AppDir's
`AppRun` too and can't be made to work outside of it without re-mounting
the AppImage, so they're left untouched and will not function; documented
here rather than silently papered over.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional

from devtools.utils import paths as pathsmod

_ICON_GLOB_PATTERNS = ("*.png", "*.svg")
_REWRITTEN_KEYS = ("Exec", "TryExec", "Icon", "Path")


class AppImageError(RuntimeError):
    """Raised for anything that stops a `devtools appimage` command."""


@dataclass
class ShortcutResult:
    app_name: str
    desktop_entry_path: Path
    icon_path: Path
    source: str  # "bundled" | "generated"


def app_name_for(appimage_path: Path, override: Optional[str] = None) -> str:
    return override or appimage_path.stem


def desktop_entry_path_for(app_name: str, applications_dir: Optional[Path] = None) -> Path:
    return (applications_dir or pathsmod.applications_dir()) / f"{app_name}.desktop"


@contextmanager
def _extracted_appdir(appimage_path: Path) -> Iterator[Path]:
    """Extract the AppImage to a throwaway temp dir; always cleaned up."""
    tmp = Path(tempfile.mkdtemp(prefix="devtools-appimage-"))
    try:
        result = subprocess.run(
            [str(appimage_path), "--appimage-extract"],
            cwd=tmp,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise AppImageError(
                f"Failed to extract '{appimage_path}' (is it executable and a valid AppImage?): "
                f"{result.stderr.strip() or result.stdout.strip()}"
            )
        appdir = tmp / "squashfs-root"
        if not appdir.is_dir():
            raise AppImageError(f"'{appimage_path}' did not produce a squashfs-root after --appimage-extract.")
        yield appdir
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def find_bundled_desktop_entry(appdir: Path) -> Optional[Path]:
    """The AppDir-root `.desktop` file, if the AppImage shipped one."""
    candidates = sorted(p for p in appdir.iterdir() if p.is_file() and p.suffix.lower() == ".desktop")
    return candidates[0] if candidates else None


def find_icon_candidates(appdir: Path) -> list[Path]:
    """png/svg files at the AppDir root, resolving symlinks (AppImages
    commonly symlink `.DirIcon` -> the real icon file)."""
    found: list[Path] = []
    for pattern in _ICON_GLOB_PATTERNS:
        found.extend(p for p in appdir.glob(pattern) if p.is_file())
    return sorted(set(found))


def resolve_bundled_icon(appdir: Path, desktop_entry: Path) -> Optional[Path]:
    """The icon file a bundled `.desktop`'s `Icon=` key actually points at
    (spec: a bare name with no path/extension, resolved by the icon theme
    -- here just "does <name>.png or <name>.svg exist at the AppDir root")."""
    icon_name = _read_key(desktop_entry.read_text(encoding="utf-8", errors="replace"), "Icon")
    if not icon_name:
        return None
    for ext in ("png", "svg"):
        candidate = appdir / f"{icon_name}.{ext}"
        if candidate.is_file():
            return candidate
    return None


def _read_key(desktop_text: str, key: str) -> Optional[str]:
    for line in desktop_text.splitlines():
        if line.strip() == "[Desktop Entry]":
            continue
        if line.startswith("[") and line.strip() != "[Desktop Entry]":
            break
        match = re.match(rf"^{re.escape(key)}=(.*)$", line)
        if match:
            return match.group(1).strip()
    return None


def adapt_bundled_desktop_entry(desktop_text: str, appimage_path: Path, icon_dst: Path) -> str:
    """Reuse a bundled `.desktop` file, rewriting only the keys that would
    otherwise point into the (about to be deleted) extraction directory."""
    replacements = {
        "Exec": f'"{appimage_path}"',
        "TryExec": str(appimage_path),
        "Icon": str(icon_dst),
    }
    out_lines: list[str] = []
    in_main_group = False
    seen_keys: set[str] = set()
    for line in desktop_text.splitlines():
        stripped = line.strip()
        if stripped == "[Desktop Entry]":
            in_main_group = True
            out_lines.append(line)
            continue
        if stripped.startswith("["):
            in_main_group = False
            out_lines.append(line)
            continue
        if in_main_group:
            key_match = re.match(r"^([A-Za-z0-9-]+)=", line)
            key = key_match.group(1) if key_match else None
            if key == "Path":
                # Pointed at the extraction dir; there's no equivalent
                # persistent working directory to substitute, so drop it.
                continue
            if key in replacements:
                out_lines.append(f"{key}={replacements[key]}")
                seen_keys.add(key)
                continue
        out_lines.append(line)

    for key in ("Exec", "Icon"):
        if key not in seen_keys:
            out_lines.append(f"{key}={replacements[key]}")
    if "StartupWMClass" not in desktop_text:
        out_lines.append(f"StartupWMClass={appimage_path.stem}")
    if not re.search(r"^Terminal=", desktop_text, re.MULTILINE):
        out_lines.append("Terminal=false")

    return "\n".join(out_lines) + "\n"


def build_generated_desktop_entry(app_name: str, appimage_path: Path, icon_dst: Path) -> str:
    return (
        "[Desktop Entry]\n"
        f"Name={app_name}\n"
        f"StartupWMClass={app_name}\n"
        f'Exec="{appimage_path}"\n'
        f"Icon={icon_dst}\n"
        "Type=Application\n"
        "Terminal=false\n"
    )


def resolve_icon_choice(candidates: list[Path], choice: str) -> Path:
    """`choice` is either a 1-based index into `candidates` (as shown by
    `--list-icons`) or a filename relative to the AppDir root."""
    if choice.isdigit():
        index = int(choice) - 1
        if 0 <= index < len(candidates):
            return candidates[index]
        raise AppImageError(f"--icon {choice} is out of range (1-{len(candidates)}).")
    for candidate in candidates:
        if candidate.name == choice:
            return candidate
    raise AppImageError(f"--icon '{choice}' does not match any icon found in the AppImage.")


def install_shortcut(
    appimage_path: Path,
    *,
    name: Optional[str] = None,
    icon_choice: Optional[str] = None,
    applications_dir: Optional[Path] = None,
    icons_dir: Optional[Path] = None,
) -> ShortcutResult:
    if not appimage_path.is_file():
        raise AppImageError(f"File not found: {appimage_path}")
    appimage_path = appimage_path.resolve()

    apps_dir = applications_dir or pathsmod.applications_dir()
    icons_dir_ = icons_dir or pathsmod.icons_dir()
    apps_dir.mkdir(parents=True, exist_ok=True)
    icons_dir_.mkdir(parents=True, exist_ok=True)

    app_name = app_name_for(appimage_path, name)

    with _extracted_appdir(appimage_path) as appdir:
        bundled = find_bundled_desktop_entry(appdir)
        icon_src = resolve_bundled_icon(appdir, bundled) if bundled else None

        if icon_src is None:
            candidates = find_icon_candidates(appdir)
            if icon_choice:
                icon_src = resolve_icon_choice(candidates, icon_choice)
            elif len(candidates) == 1:
                icon_src = candidates[0]
            elif not candidates:
                raise AppImageError(f"No .png or .svg icon found at the root of '{appimage_path.name}'.")
            else:
                listing = "\n".join(f"  {i}) {p.name}" for i, p in enumerate(candidates, start=1))
                raise AppImageError(
                    f"Multiple icons found in '{appimage_path.name}'; pick one with --icon:\n{listing}"
                )

        icon_dst = icons_dir_ / f"{app_name}{icon_src.suffix}"
        shutil.copy(icon_src, icon_dst)

        desktop_entry_path = desktop_entry_path_for(app_name, apps_dir)
        if bundled is not None:
            text = adapt_bundled_desktop_entry(bundled.read_text(encoding="utf-8", errors="replace"), appimage_path, icon_dst)
            source = "bundled"
        else:
            text = build_generated_desktop_entry(app_name, appimage_path, icon_dst)
            source = "generated"
        desktop_entry_path.write_text(text, encoding="utf-8")

    return ShortcutResult(app_name=app_name, desktop_entry_path=desktop_entry_path, icon_path=icon_dst, source=source)


def list_icons(appimage_path: Path) -> list[str]:
    """Icon filenames available at the AppDir root, for `--list-icons`."""
    if not appimage_path.is_file():
        raise AppImageError(f"File not found: {appimage_path}")
    with _extracted_appdir(appimage_path.resolve()) as appdir:
        return [p.name for p in find_icon_candidates(appdir)]


def remove_shortcut(app_name: str, applications_dir: Optional[Path] = None, icons_dir: Optional[Path] = None) -> bool:
    """Remove a previously installed launcher + icon. Returns True if
    anything was actually removed."""
    apps_dir = applications_dir or pathsmod.applications_dir()
    icons_dir_ = icons_dir or pathsmod.icons_dir()

    removed = False
    desktop_entry_path = desktop_entry_path_for(app_name, apps_dir)
    if desktop_entry_path.is_file():
        desktop_entry_path.unlink()
        removed = True

    if icons_dir_.is_dir():
        for icon_file in icons_dir_.glob(f"{app_name}.*"):
            icon_file.unlink()
            removed = True

    return removed
