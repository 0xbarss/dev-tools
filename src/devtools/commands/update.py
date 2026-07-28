"""`devtools update` — self-update check against PyPI (or a configured index);
explicit opt-in, never runs automatically (spec §7).
"""

from __future__ import annotations

import subprocess
import sys

import typer

from devtools import __version__
from devtools.commands._shared import fail
from devtools.core.exit_codes import GENERAL_ERROR, INVALID_USAGE

app = typer.Typer()

_PYPI_JSON_URL = "https://pypi.org/pypi/devtools/json"


@app.command()
def update(
    ctx: typer.Context,
    check: bool = typer.Option(False, "--check", help="Only check for a newer version; don't install it."),
    index_url: str = typer.Option(_PYPI_JSON_URL, "--index-url", help="Package index metadata URL to check against."),
) -> None:
    """Check for (or install) a newer devtools release. Never runs automatically."""
    state = ctx.obj
    if not state.settings.allow_network:
        fail(
            ctx,
            INVALID_USAGE,
            "`update` requires network access. Set allow_network = true in config.toml, "
            "then re-run `devtools update`.",
        )

    latest = _fetch_latest_version(index_url)
    if latest is None:
        fail(ctx, GENERAL_ERROR, f"Could not reach {index_url} to check for updates.")

    if state.output.is_json:
        state.output.emit_json({"current_version": __version__, "latest_version": latest, "update_available": latest != __version__})
        return

    if latest == __version__:
        state.output.print(f"devtools {__version__} is up to date.")
        return

    state.output.print(f"A newer version is available: {__version__} -> {latest}")
    if check:
        return

    result = subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "devtools"])
    if result.returncode != 0:
        fail(ctx, GENERAL_ERROR, "pip install --upgrade devtools failed; see output above.")
    state.output.print(f"[green]Updated to {latest}.[/green]")


def _fetch_latest_version(index_url: str) -> str | None:
    import json
    import urllib.request

    try:
        with urllib.request.urlopen(index_url, timeout=10) as resp:  # noqa: S310 - explicit opt-in network call
            data = json.load(resp)
        return data.get("info", {}).get("version")
    except Exception:
        return None
