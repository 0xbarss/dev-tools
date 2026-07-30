"""`devtools ci` — CI pipeline scaffolding.

Currently one subcommand, `ci init`, which writes a ready-made GitHub
Actions or GitLab CI config that shells out to devtools' existing
`--ci`/`--check` exit-code hooks (`doctor --ci`, `deps --check`).
"""

from __future__ import annotations

import typer

from devtools.commands._shared import fail
from devtools.core.ci_templates import render_ci_config
from devtools.core.exit_codes import FILESYSTEM_ERROR, INVALID_USAGE

app = typer.Typer(help="Scaffold CI pipeline configs.")


@app.command("init")
def init(
    ctx: typer.Context,
    provider: str = typer.Option("github", "--provider", help="CI provider to generate a config for: 'github' or 'gitlab'."),
    project_name: str = typer.Option(None, "--project-name", help="Project name devtools should register in the generated config (default: current directory name)."),
    force: bool = typer.Option(False, "--force", help="Overwrite an existing CI config file."),
) -> None:
    """Emit a ready-made CI config that runs `devtools doctor --ci` / `deps --check`."""
    state = ctx.obj
    from pathlib import Path

    name = project_name or Path.cwd().name

    try:
        rel_path, content = render_ci_config(provider, name)
    except ValueError as exc:
        fail(ctx, INVALID_USAGE, str(exc))

    out_path = Path.cwd() / rel_path
    if out_path.exists() and not force:
        fail(ctx, FILESYSTEM_ERROR, f"{rel_path} already exists. Use --force to overwrite.")

    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(content, encoding="utf-8")
    except OSError as exc:
        fail(ctx, FILESYSTEM_ERROR, f"Could not write {rel_path}: {exc}")

    if state.output.is_json:
        state.output.emit_json({"provider": provider, "path": rel_path})
    else:
        state.output.print(f"[green]Wrote {rel_path}[/green] ({provider} CI config for project '{name}')")
