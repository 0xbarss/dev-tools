"""`devtools init` — bootstrap ~/.config/devtools/ (spec §6).

`ensure_initialized()` is called implicitly (and idempotently) from cli.py's
root callback before every command runs, so a fresh install never hard-crashes
on a missing config directory.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from devtools.core import config as cfgmod
from devtools.models.project import Project
from devtools.utils import paths as pathsmod

app = typer.Typer(help="Bootstrap the devtools config directory.")


def ensure_initialized() -> bool:
    """Idempotently create the config dir, config.toml, and projects.json.

    Returns True if anything was created (first run), False if everything
    already existed.
    """
    created = False
    if not pathsmod.config_dir().exists():
        pathsmod.ensure_config_dir()
        created = True
    if not pathsmod.config_file_path().is_file():
        cfgmod.save_settings(cfgmod.Settings())
        created = True
    if not pathsmod.projects_file_path().is_file():
        cfgmod.save_projects({})
        created = True
    return created


@app.command()
def init(
    ctx: typer.Context,
    register_here: bool = typer.Option(False, "--register-here", help="Also register the current directory as a project."),
    name: Optional[str] = typer.Option(None, "--name", help="Project name to use with --register-here (default: directory name)."),
) -> None:
    """Bootstrap ~/.config/devtools/config.toml and projects.json."""
    state = ctx.obj
    created = ensure_initialized()
    if created:
        state.output.print(f"[green]Initialized devtools config at {pathsmod.config_dir()}[/green]")
    else:
        state.output.print(f"devtools is already initialized at {pathsmod.config_dir()}")

    if register_here:
        cwd = Path.cwd()
        proj_name = name or cwd.name
        projects = cfgmod.load_projects()
        projects[proj_name] = Project(name=proj_name, path=str(cwd))
        cfgmod.save_projects(projects)
        state.output.print(f"Registered project '{proj_name}' -> {cwd}")
