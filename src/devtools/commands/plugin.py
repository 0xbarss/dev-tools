"""`devtools plugin` — plugin management (backlog #8). Stays thin per the
existing `commands/` convention; all real logic lives in
`core/plugin_engine.py`."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from devtools.core import plugin_engine
from devtools.core.exit_codes import GENERAL_ERROR, SUCCESS
from devtools.core.output import render_table

app = typer.Typer(help="Manage devtools plugins (entry-point packages and single-file script plugins).")


@app.command("list")
def list_plugins(ctx: typer.Context) -> None:
    """List every discovered plugin (entry-point packages and installed
    script plugins), with load/API-compatibility status."""
    state = ctx.obj
    infos = plugin_engine.list_plugins()

    if state.output.is_json:
        state.output.emit_json(
            {
                "plugins": [
                    {
                        "name": i.name,
                        "source": i.source,
                        "location": i.location,
                        "api_version": i.api_version,
                        "api_compatible": i.api_compatible,
                        "error": i.error,
                    }
                    for i in infos
                ]
            }
        )
        return

    if not infos:
        state.output.print(
            "[dim]No plugins installed. Add a script plugin with `devtools plugin install ./my-check.py`, "
            f"or a real package via `pip install ...` and a `{plugin_engine.ENTRY_POINT_GROUP}` entry point.[/dim]"
        )
        return

    def _status(i: plugin_engine.PluginInfo) -> str:
        if i.error:
            return f"error: {i.error}"
        if i.api_compatible is False:
            return f"incompatible (api {i.api_version}, expected {plugin_engine.CURRENT_API_VERSION})"
        return "ok"

    render_table(
        state.output,
        "Plugins",
        ["name", "source", "location", "status"],
        [[i.name, i.source, i.location, _status(i)] for i in infos],
    )
    state.output.info(
        "Plugins run with full process privileges -- there is no sandboxing. Only install plugins you trust.",
        level=1,
    )


@app.command("install")
def install(
    ctx: typer.Context,
    path: Path = typer.Argument(..., help="Path to a single-file plugin script (a .py file defining register(app))."),
) -> None:
    """Install a single-file script plugin. For a proper Python package
    declaring a `devtools.plugins` entry point, `pip install` it instead --
    devtools doesn't reimplement a package manager."""
    state = ctx.obj
    try:
        info = plugin_engine.install_script_plugin(path)
    except plugin_engine.PluginError as exc:
        state.output.error(str(exc))
        state.exit_code = GENERAL_ERROR
        raise typer.Exit(code=GENERAL_ERROR) from exc

    state.output.print(f"[green]Installed plugin '{info.name}' from {path}.[/green]")
    if info.api_version and info.api_version != plugin_engine.CURRENT_API_VERSION:
        state.output.warn(
            f"Plugin declares DEVTOOLS_API_VERSION={info.api_version!r}, but this devtools speaks "
            f"{plugin_engine.CURRENT_API_VERSION!r}. It will still load, but may not work correctly."
        )
    state.exit_code = SUCCESS


@app.command("remove")
def remove(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Name of a script plugin to remove (see `devtools plugin list`)."),
) -> None:
    """Remove a script plugin. Entry-point (pip-installed) plugins aren't
    managed here -- `pip uninstall` the package that provides them."""
    state = ctx.obj
    removed = plugin_engine.remove_script_plugin(name)
    if not removed:
        state.output.error(
            f"No script plugin named '{name}'. If it's an entry-point plugin, `pip uninstall` its package instead."
        )
        state.exit_code = GENERAL_ERROR
        raise typer.Exit(code=GENERAL_ERROR)
    state.output.print(f"[green]Removed plugin '{name}'.[/green]")
