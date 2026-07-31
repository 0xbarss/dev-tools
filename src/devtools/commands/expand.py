"""`devtools expand` — the inverse of `collect`: turns a file previously
produced by `devtools collect` back into a real project directory on disk.
Sits next to `new` the same way `project add` sits next to `new`: `expand`
creates the project on disk from someone else's `collect` output, and can
optionally register it in the same step so the very next command can be
`devtools doctor <name>`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from devtools.commands._shared import fail
from devtools.core import config as cfgmod
from devtools.core.exit_codes import FILESYSTEM_ERROR, GENERAL_ERROR, INVALID_USAGE
from devtools.core.expand_engine import ExpandParseError, UnsafePathError, expand as expand_engine
from devtools.models.project import Project

app = typer.Typer()


@app.command("expand")
def expand(
    ctx: typer.Context,
    source: Path = typer.Argument(..., help="A file previously written by `devtools collect` (markdown, json, or text)."),
    target: Path = typer.Argument(..., help="Directory to write the collected files into (created if missing)."),
    fmt: Optional[str] = typer.Option(None, "--format", help="Force the source format instead of auto-detecting from its extension/content: markdown, json, or text."),
    force: bool = typer.Option(False, "--force", help="Overwrite files that already exist at target with different content."),
    name: Optional[str] = typer.Option(None, "--name", help="Project name to register as (default: target's directory name)."),
    register: bool = typer.Option(True, "--register/--no-register", help="Register the expanded project with devtools under `name`."),
) -> None:
    """Parse a `collect`-produced file and materialize it back into a real
    project directory -- e.g. to reconstruct a repo from a markdown dump
    someone pasted into a chat, or to hand off a `collect` file and let the
    recipient turn it back into working files."""
    state = ctx.obj

    if fmt is not None and fmt not in ("markdown", "json", "text"):
        fail(ctx, INVALID_USAGE, "--format must be one of: markdown, json, text")
        return

    if not source.is_file():
        fail(ctx, INVALID_USAGE, f"Not a file: {source}")
        return

    try:
        result = expand_engine(source, target, fmt=fmt, force=force)
    except ExpandParseError as exc:
        fail(ctx, INVALID_USAGE, str(exc))
        return
    except UnsafePathError as exc:
        fail(ctx, GENERAL_ERROR, str(exc))
        return
    except FileExistsError as exc:
        fail(ctx, GENERAL_ERROR, str(exc))
        return
    except OSError as exc:
        fail(ctx, FILESYSTEM_ERROR, f"Could not write to {target}: {exc}")
        return

    project_name = name or result.target.name
    registered = False
    if register:
        projects = cfgmod.load_projects()
        if project_name not in projects:
            projects[project_name] = Project(name=project_name, path=str(result.target))
            cfgmod.save_projects(projects)
            registered = True

    if state.output.is_json:
        state.output.emit_json(
            {
                "target": str(result.target),
                "written": result.written,
                "skipped_existing": result.skipped_existing,
                "registered": registered,
                "project": project_name if registered else None,
            }
        )
        return

    state.output.print(
        f"[green]Expanded {len(result.written)} file(s)[/green] into {result.target}"
        + (f" ({len(result.skipped_existing)} already up to date)" if result.skipped_existing else "")
        + "."
    )
    if registered:
        state.output.print(f"Registered as project '{project_name}' — try `devtools doctor {project_name}`.")
    elif register:
        state.output.print(f"[yellow]A project named '{project_name}' was already registered; left it as-is.[/yellow]")
