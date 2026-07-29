"""`devtools ui` — launch the interactive TUI (backlog #6, P1, Large).

`textual` is an optional dependency (`pip install "devtools[tui]"`),
matching the same lazy-import pattern `mcp-serve` uses for the `mcp`
package: the core `devtools` install never requires a TUI framework just
to run `stats`/`lint`/etc.
"""

from __future__ import annotations

from typing import Optional

import typer

from devtools.commands._shared import resolve_project
from devtools.core.exit_codes import GENERAL_ERROR

app = typer.Typer()

_TUI_INSTALL_HINT = (
    "The `textual` package is required for `devtools ui`. Install it with "
    '`pip install "devtools[tui]"` (or `pip install textual`), then re-run `devtools ui`.'
)


@app.command()
def ui(
    ctx: typer.Context,
    project: Optional[str] = typer.Argument(None, help="Open straight to this project's dashboard instead of the project picker."),
) -> None:
    """Launch the interactive TUI: a project picker plus a per-project
    dashboard (health score, stats summary, doctor findings) -- the same
    `core/` engines the scriptable CLI uses, just explorable instead of
    one-shot. Press 'q' to quit, 'r' to refresh, Escape to go back."""
    state = ctx.obj

    if project is not None:
        # Resolve eagerly so a typo in the project name fails fast with
        # the CLI's normal error handling, rather than inside the TUI.
        resolve_project(ctx, project)

    try:
        from devtools.tui.app import run_tui
    except ImportError as exc:
        state.output.error(_TUI_INSTALL_HINT)
        state.exit_code = GENERAL_ERROR
        raise typer.Exit(code=GENERAL_ERROR) from exc

    run_tui(initial_project=project)
