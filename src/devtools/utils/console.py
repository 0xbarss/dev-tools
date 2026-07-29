"""Builds the shared OutputContext from the global CLI flags (spec §5)."""

from __future__ import annotations

import os

from rich.console import Console

from devtools.core.output import OutputContext, OutputFormat


def build_output_context(
    json: bool = False,
    fmt: str | None = None,
    quiet: bool = False,
    verbose: int = 0,
    no_color: bool = False,
) -> OutputContext:
    no_color = no_color or bool(os.environ.get("NO_COLOR"))
    if json:
        resolved_fmt = OutputFormat.JSON
    elif fmt == "markdown":
        resolved_fmt = OutputFormat.MARKDOWN
    else:
        resolved_fmt = OutputFormat.RICH

    console = Console(no_color=no_color or resolved_fmt == OutputFormat.JSON, highlight=False)
    return OutputContext(
        fmt=resolved_fmt,
        quiet=quiet,
        verbose=verbose,
        no_color=no_color,
        console=console,
    )