"""`devtools appimage` -- install/remove a `.desktop` launcher + icon for an
AppImage, reusing the AppImage's own bundled `.desktop` file when it has
one instead of generating one from scratch. Replaces the old standalone
`script.sh`; see `core/appimage_engine.py` for the extraction/rewrite logic.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from devtools.commands._shared import fail
from devtools.core.appimage_engine import AppImageError, install_shortcut, list_icons, remove_shortcut
from devtools.core.exit_codes import FILESYSTEM_ERROR, INVALID_USAGE

app = typer.Typer(help="Install/remove a .desktop launcher + icon for an AppImage.")


@app.command("install")
def install(
    ctx: typer.Context,
    appimage_path: Path = typer.Argument(..., help="Path to the .AppImage file."),
    name: Optional[str] = typer.Option(None, "--name", help="Launcher name (default: the AppImage's filename stem)."),
    icon: Optional[str] = typer.Option(
        None, "--icon", help="Icon to use when it can't be resolved automatically: a 1-based index from --list-icons, or an icon filename."
    ),
    list_icons_only: bool = typer.Option(
        False, "--list-icons", help="List the icons found inside the AppImage and exit, without installing anything."
    ),
) -> None:
    """Extract the AppImage, reuse its bundled .desktop entry if it has one
    (only rewriting Exec/TryExec/Icon, and dropping Path=, since those would
    otherwise point at the temporary extraction directory), and install the
    icon + launcher under the XDG applications/icons directories."""
    state = ctx.obj

    if not appimage_path.is_file():
        fail(ctx, FILESYSTEM_ERROR, f"File not found: {appimage_path}")
        return

    if list_icons_only:
        try:
            icons = list_icons(appimage_path)
        except AppImageError as exc:
            fail(ctx, FILESYSTEM_ERROR, str(exc))
            return
        if state.output.is_json:
            state.output.emit_json({"appimage": str(appimage_path), "icons": icons})
            return
        if not icons:
            state.output.print("No .png or .svg icons found at the root of this AppImage.")
            return
        for i, icon_name in enumerate(icons, start=1):
            state.output.print(f"  {i}) {icon_name}")
        return

    try:
        result = install_shortcut(appimage_path, name=name, icon_choice=icon)
    except AppImageError as exc:
        fail(ctx, INVALID_USAGE, str(exc))
        return

    if state.output.is_json:
        state.output.emit_json(
            {
                "app_name": result.app_name,
                "desktop_entry_path": str(result.desktop_entry_path),
                "icon_path": str(result.icon_path),
                "source": result.source,
            }
        )
        return

    if result.source == "bundled":
        state.output.print(f"[green]Installed '{result.app_name}'[/green] using its bundled desktop entry.")
    else:
        state.output.print(f"[green]Installed '{result.app_name}'[/green] (no bundled desktop entry found; generated one).")
    state.output.print(f"  Launcher: {result.desktop_entry_path}")
    state.output.print(f"  Icon:     {result.icon_path}")


@app.command("remove")
def remove(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Launcher name to remove (as passed to --name, or the AppImage's filename stem)."),
) -> None:
    """Remove a previously installed launcher and its icon."""
    state = ctx.obj
    removed = remove_shortcut(name)

    if state.output.is_json:
        state.output.emit_json({"app_name": name, "removed": removed})
        return

    if removed:
        state.output.print(f"[green]Removed '{name}'.[/green]")
    else:
        state.output.print(f"Nothing to remove for '{name}'.")
