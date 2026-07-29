"""`devtools config` — first-class config.toml editing (vs. hand-editing
the file directly). Thin wiring over `core/config.py`'s get/set helpers."""

from __future__ import annotations

import typer

from devtools.commands._shared import fail
from devtools.core import config as cfgmod
from devtools.core.exit_codes import INVALID_USAGE
from devtools.core.output import render_kv

app = typer.Typer(help="Get, set, and list devtools configuration values.")


@app.command("get")
def get(ctx: typer.Context, key: str = typer.Argument(..., help="Dotted config key, e.g. allow_network or project_overrides.api.ignored_dirs.")) -> None:
    """Print a single config value."""
    state = ctx.obj
    settings = cfgmod.load_settings(state.config_path)
    try:
        value = cfgmod.get_config_value(settings, key)
    except cfgmod.ConfigKeyError:
        fail(ctx, INVALID_USAGE, f"Unknown config key: {key!r}. Run `devtools config list` to see available keys.")

    if state.output.is_json:
        state.output.emit_json({key: value})
    else:
        state.output.print(str(value))


@app.command("set")
def set_(
    ctx: typer.Context,
    key: str = typer.Argument(..., help="Dotted config key, e.g. allow_network or project_overrides.api.ignored_dirs."),
    value: str = typer.Argument(..., help="New value. Booleans: true/false. Lists: comma-separated."),
) -> None:
    """Set a config value and persist it to config.toml."""
    state = ctx.obj
    settings = cfgmod.load_settings(state.config_path)
    try:
        cfgmod.set_config_value(settings, key, value)
    except cfgmod.ConfigKeyError:
        fail(ctx, INVALID_USAGE, f"Unknown config key: {key!r}. Run `devtools config list` to see available keys.")
    except ValueError as exc:
        fail(ctx, INVALID_USAGE, str(exc))

    path = cfgmod.save_settings(settings, state.config_path)
    state.output.print(f"[green]Set {key} = {value}[/green] (saved to {path})")


@app.command("list")
def list_(ctx: typer.Context) -> None:
    """Show every current config value."""
    state = ctx.obj
    settings = cfgmod.load_settings(state.config_path)
    render_kv(state.output, "devtools config", cfgmod.all_config_values(settings))