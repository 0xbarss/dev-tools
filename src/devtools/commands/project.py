"""`devtools project` — manage registered repositories (spec §6)."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from devtools.commands._shared import fail
from devtools.core import config as cfgmod
from devtools.core.exit_codes import INVALID_USAGE, PROJECT_NOT_FOUND
from devtools.core.output import render_kv, render_table
from devtools.models.project import Project

app = typer.Typer(help="Manage registered repositories.")


@app.command("add")
def add(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Name to register the project under."),
    path: Optional[Path] = typer.Argument(None, help="Path to the project (default: current directory)."),
    force: bool = typer.Option(False, "--force", help="Overwrite an existing project with the same name."),
) -> None:
    """Register a repository. `add` without a path defaults to the current directory."""
    state = ctx.obj
    target = (path or Path.cwd()).expanduser()
    if not target.is_dir():
        fail(ctx, INVALID_USAGE, f"Path does not exist or is not a directory: {target}")

    projects = cfgmod.load_projects()
    if name in projects and not force:
        fail(ctx, INVALID_USAGE, f"Project '{name}' already exists. Use --force to overwrite.")

    projects[name] = Project(name=name, path=str(target))
    cfgmod.save_projects(projects)
    state.output.print(f"[green]Registered '{name}' -> {target}[/green]")


@app.command("remove")
def remove(ctx: typer.Context, name: str = typer.Argument(...)) -> None:
    """Unregister a project (does not delete anything on disk)."""
    state = ctx.obj
    projects = cfgmod.load_projects()
    if name not in projects:
        fail(ctx, PROJECT_NOT_FOUND, f"Project '{name}' is not registered.")
    del projects[name]
    cfgmod.save_projects(projects)
    state.output.print(f"Removed '{name}'")


@app.command("rename")
def rename(ctx: typer.Context, old_name: str = typer.Argument(...), new_name: str = typer.Argument(...)) -> None:
    """Rename a registered project."""
    state = ctx.obj
    projects = cfgmod.load_projects()
    if old_name not in projects:
        fail(ctx, PROJECT_NOT_FOUND, f"Project '{old_name}' is not registered.")
    if new_name in projects:
        fail(ctx, INVALID_USAGE, f"A project named '{new_name}' already exists.")
    proj = projects.pop(old_name)
    proj.name = new_name
    projects[new_name] = proj
    cfgmod.save_projects(projects)

    settings = cfgmod.load_settings(state.config_path)
    if settings.default_project == old_name:
        settings.default_project = new_name
        cfgmod.save_settings(settings, state.config_path)

    state.output.print(f"Renamed '{old_name}' -> '{new_name}'")


@app.command("list")
def list_projects(ctx: typer.Context) -> None:
    """List all registered projects."""
    state = ctx.obj
    projects = cfgmod.load_projects()
    settings = cfgmod.load_settings(state.config_path)
    rows = [
        [name, proj.path, "yes" if proj.exists() else "MISSING", "yes" if name == settings.default_project else ""]
        for name, proj in sorted(projects.items())
    ]
    render_table(state.output, "Registered projects", ["name", "path", "exists", "default"], rows, json_key="projects")


@app.command("default")
def set_default(ctx: typer.Context, name: str = typer.Argument(...)) -> None:
    """Set the default project (used when no --project/positional project is given)."""
    state = ctx.obj
    projects = cfgmod.load_projects()
    if name not in projects:
        fail(ctx, PROJECT_NOT_FOUND, f"Project '{name}' is not registered.")
    settings = cfgmod.load_settings(state.config_path)
    settings.default_project = name
    cfgmod.save_settings(settings, state.config_path)
    state.output.print(f"Default project set to '{name}'")


@app.command("show")
def show(ctx: typer.Context, name: str = typer.Argument(...)) -> None:
    """Show a project's path, last-collected time, and cached stats."""
    state = ctx.obj
    projects = cfgmod.load_projects()
    if name not in projects:
        fail(ctx, PROJECT_NOT_FOUND, f"Project '{name}' is not registered.")
    proj = projects[name]
    data = {
        "name": proj.name,
        "path": proj.path,
        "exists": proj.exists(),
        "last_collected": proj.last_collected or "never",
        "cached_stats": proj.cached_stats or {},
    }
    render_kv(state.output, f"Project: {name}", data)
