"""`devtools new` — scaffold a new project from a built-in template
(backlog #33, P2). Sits next to `project add`: `new` creates the project
on disk, and can optionally register it in the same step so the very next
command can be `devtools doctor <name>`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from devtools.commands._shared import fail
from devtools.core import config as cfgmod
from devtools.core.exit_codes import GENERAL_ERROR, INVALID_USAGE
from devtools.core.scaffold_engine import TEMPLATES, scaffold
from devtools.models.project import Project

app = typer.Typer()


def _complete_template(incomplete: str) -> list[str]:
    return [t for t in TEMPLATES if t.startswith(incomplete)]


@app.command("new")
def new(
    ctx: typer.Context,
    template: str = typer.Argument(..., autocompletion=_complete_template, help=f"Template to use. One of: {', '.join(sorted(TEMPLATES))}."),
    name: str = typer.Argument(..., help="Name of the new project (also used as the directory name unless --path is given)."),
    path: Optional[Path] = typer.Option(None, "--path", help="Directory to create (default: ./<name>)."),
    license_: bool = typer.Option(True, "--license/--no-license", help="Include an MIT LICENSE file."),
    author: str = typer.Option("Your Name", "--author", help="Name to put in LICENSE."),
    register: bool = typer.Option(True, "--register/--no-register", help="Register the new project with devtools under `name`."),
) -> None:
    """Scaffold a new project from a built-in template. Run with no
    matching template to see the available list in the error message."""
    state = ctx.obj

    if template not in TEMPLATES:
        fail(ctx, INVALID_USAGE, f"Unknown template '{template}'. Available templates:\n" + "\n".join(f"  - {t.name}: {t.description}" for t in TEMPLATES.values()))
        return

    target = (path or Path.cwd() / name).expanduser()

    try:
        created_files = scaffold(template, target, name, license_=license_, author=author)
    except FileExistsError as exc:
        fail(ctx, INVALID_USAGE, str(exc))
        return
    except ValueError as exc:
        fail(ctx, GENERAL_ERROR, str(exc))
        return

    registered = False
    if register:
        projects = cfgmod.load_projects()
        if name not in projects:
            projects[name] = Project(name=name, path=str(target))
            cfgmod.save_projects(projects)
            registered = True

    if state.output.is_json:
        state.output.emit_json({"template": template, "path": str(target), "files": created_files, "registered": registered})
        return

    state.output.print(f"[green]Created '{name}'[/green] at {target} from template '{template}' ({len(created_files)} file(s)).")
    if registered:
        state.output.print(f"Registered as project '{name}' — try `devtools doctor {name}`.")
    elif register:
        state.output.print(f"[yellow]A project named '{name}' was already registered; left it as-is.[/yellow]")
