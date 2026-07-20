"""Helpers shared by every command module.

Not a command itself (no @app.command() here) — just the plumbing that
resolves a project name/path and builds its IgnoreRules the same way
everywhere, so `collect`, `bundle`, `grep`, `tree`, `stats`, `doctor`, etc.
never disagree about what "the project" or "ignored" means.
"""

from __future__ import annotations

import typer

from devtools.core import config as cfgmod
from devtools.core.exit_codes import FILESYSTEM_ERROR, PROJECT_NOT_FOUND
from devtools.core.ignore_rules import IgnoreRules
from devtools.models.project import Project


def get_state(ctx: typer.Context):
    return ctx.obj


def fail(ctx: typer.Context, code: int, message: str) -> None:
    """Print an error, record the exit code for history logging, and exit."""
    state = get_state(ctx)
    state.output.error(message)
    state.exit_code = code
    raise typer.Exit(code=code)


def resolve_project(ctx: typer.Context, cli_project: str | None = None) -> Project:
    state = get_state(ctx)
    name = cfgmod.resolve_project_name(cli_project or state.project_arg, state.settings, state.projects)
    if not name:
        fail(
            ctx,
            PROJECT_NOT_FOUND,
            "No project specified and no default project configured. "
            "Pass a project name, use --project, or run `devtools project add <name> <path>` "
            "and `devtools project default <name>`.",
        )
    project = state.projects.get(name)
    if project is None:
        fail(ctx, PROJECT_NOT_FOUND, f"Project '{name}' is not registered. Run `devtools project list` to see registered projects.")
    if not project.exists():
        fail(ctx, FILESYSTEM_ERROR, f"Project '{name}' path does not exist: {project.path}")
    return project


def build_ignore_rules(
    ctx: typer.Context,
    project: Project,
    extra_excludes: list[str] | None = None,
    use_gitignore: bool = True,
) -> IgnoreRules:
    state = get_state(ctx)
    ignored_dirs = state.settings.ignored_dirs_for(project.name)
    return IgnoreRules.build(
        root=project.resolved_path,
        base_ignored_dirs=ignored_dirs,
        extra_excludes=extra_excludes,
        use_gitignore=use_gitignore,
    )
