"""`devtools ignore` — manage the ignore rules shared by collect/bundle/grep/
tree/stats (spec §7), instead of forcing users to hand-edit config.toml.
"""

from __future__ import annotations

from typing import Optional

import typer

from devtools.core import config as cfgmod
from devtools.models.settings import ProjectOverride
from devtools.core.output import render_table

app = typer.Typer(help="Manage ignore rules shared across collect/bundle/grep/tree/stats.")


@app.command("add")
def add(
    ctx: typer.Context,
    pattern: str = typer.Argument(..., help="Glob pattern to ignore, e.g. '*.lock'."),
    project: Optional[str] = typer.Option(None, "--project", help="Add to this project's overrides instead of the global list."),
) -> None:
    """Add an ignore pattern, globally or to a specific project's overrides."""
    state = ctx.obj
    settings = cfgmod.load_settings(state.config_path)
    target_project = project or state.project_arg

    if target_project:
        override = settings.project_overrides.setdefault(target_project, ProjectOverride())
        if pattern not in override.ignored_dirs:
            override.ignored_dirs.append(pattern)
        scope = f"project '{target_project}'"
    else:
        if pattern not in settings.ignored_dirs:
            settings.ignored_dirs.append(pattern)
        scope = "global"

    cfgmod.save_settings(settings, state.config_path)
    state.output.print(f"[green]Added '{pattern}' to {scope} ignore rules.[/green]")


@app.command("remove")
def remove(
    ctx: typer.Context,
    pattern: str = typer.Argument(...),
    project: Optional[str] = typer.Option(None, "--project", help="Remove from this project's overrides instead of the global list."),
) -> None:
    """Remove an ignore pattern."""
    state = ctx.obj
    settings = cfgmod.load_settings(state.config_path)
    target_project = project or state.project_arg
    removed = False

    if target_project and target_project in settings.project_overrides:
        override = settings.project_overrides[target_project]
        if pattern in override.ignored_dirs:
            override.ignored_dirs.remove(pattern)
            removed = True
    elif not target_project and pattern in settings.ignored_dirs:
        settings.ignored_dirs.remove(pattern)
        removed = True

    if removed:
        cfgmod.save_settings(settings, state.config_path)
        state.output.print(f"[green]Removed '{pattern}'.[/green]")
    else:
        state.output.print(f"'{pattern}' was not found in the relevant ignore list.")


@app.command("list")
def list_rules(
    ctx: typer.Context,
    project: Optional[str] = typer.Argument(None, help="Show the effective rules (global + overrides) for this project."),
) -> None:
    """Show effective ignore rules: global + that project's overrides."""
    state = ctx.obj
    settings = cfgmod.load_settings(state.config_path)
    target_project = project or state.project_arg

    rows = [[p, "global"] for p in settings.ignored_dirs]
    if target_project and target_project in settings.project_overrides:
        rows += [[p, f"project:{target_project}"] for p in settings.project_overrides[target_project].ignored_dirs]

    render_table(state.output, "Effective ignore rules", ["pattern", "scope"], rows, json_key="rules")