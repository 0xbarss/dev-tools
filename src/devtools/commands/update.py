"""`devtools update` — reinstalls devtools from its local source checkout via
`uv tool install "<source>[<extras>]"`; explicit opt-in, never runs
automatically.

There's no published package/registry to check for devtools (it's a
personal, locally-developed toolkit, not something on PyPI) -- so "update"
here means "rebuild and reinstall from the source checkout on disk", not
"check some index for a newer release". `--check` compares the version in
that checkout's pyproject.toml against the currently-installed version
without installing anything.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Optional

import typer

try:
    import tomllib  # Python >= 3.11
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]

from devtools import __version__
from devtools.commands._shared import fail
from devtools.core.exit_codes import GENERAL_ERROR, INVALID_USAGE

app = typer.Typer()


@app.command()
def update(
    ctx: typer.Context,
    check: bool = typer.Option(False, "--check", help="Only report the source checkout's version vs. the installed one; don't reinstall."),
    source: Optional[Path] = typer.Option(None, "--source", help="Path to the devtools source checkout (default: config.toml's update_source_path)."),
) -> None:
    """Reinstall devtools from a local source checkout via `uv tool install`,
    picking up any local code changes. Never runs automatically."""
    state = ctx.obj
    source_path = (source or Path(state.settings.update_source_path)).expanduser()

    pyproject = source_path / "pyproject.toml"
    if not pyproject.is_file():
        fail(
            ctx,
            INVALID_USAGE,
            f"No pyproject.toml found at {source_path}. Set the right path with "
            f"`devtools config set update_source_path <path>`, or pass --source.",
        )
        return

    source_version = _read_project_version(pyproject)

    if check:
        if state.output.is_json:
            state.output.emit_json(
                {
                    "installed_version": __version__,
                    "source_version": source_version,
                    "source_path": str(source_path),
                    "up_to_date": source_version == __version__,
                }
            )
            return
        if source_version is None:
            state.output.print(f"[yellow]Could not read a version from {pyproject}.[/yellow]")
        elif source_version == __version__:
            state.output.print(f"devtools {__version__} is up to date with {source_path}.")
        else:
            state.output.print(f"Source checkout at {source_path} is version {source_version} (installed: {__version__}).")
        return

    if not state.settings.allow_network:
        fail(
            ctx,
            INVALID_USAGE,
            "`update` needs network access to resolve dependencies. Set allow_network = true "
            "in config.toml, then re-run `devtools update`.",
        )
        return

    if shutil.which("uv") is None:
        fail(
            ctx,
            GENERAL_ERROR,
            "`uv` was not found on PATH. Install it first: https://docs.astral.sh/uv/getting-started/installation/",
        )
        return

    extras = ",".join(state.settings.update_extras)
    target = f"{source_path}[{extras}]" if extras else str(source_path)

    state.output.print(f'Running: uv tool install "{target}"')
    result = subprocess.run(["uv", "tool", "install", target])
    if result.returncode != 0:
        fail(ctx, GENERAL_ERROR, "`uv tool install` failed; see output above.")
        return

    if state.output.is_json:
        state.output.emit_json({"installed_from": str(source_path), "extras": state.settings.update_extras})
        return
    state.output.print(f"[green]Reinstalled devtools from {source_path}.[/green]")


def _read_project_version(pyproject: Path) -> str | None:
    try:
        with pyproject.open("rb") as f:
            data = tomllib.load(f)
        return data.get("project", {}).get("version")
    except (OSError, tomllib.TOMLDecodeError):
        return None
