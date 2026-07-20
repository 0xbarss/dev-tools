"""Shared output rendering so every command's --json/--format markdown/Rich
table output looks and behaves the same way (spec §5, "Output modes").
"""

from __future__ import annotations

import json as _json
import sys
from dataclasses import dataclass
from enum import Enum

try:
    import orjson
except ImportError:  # pragma: no cover
    orjson = None  # type: ignore[assignment]

from rich.console import Console
from rich.table import Table


class OutputFormat(str, Enum):
    RICH = "rich"
    JSON = "json"
    MARKDOWN = "markdown"


@dataclass
class OutputContext:
    """Carries the global output flags (§5) through to every command."""

    fmt: OutputFormat = OutputFormat.RICH
    quiet: bool = False
    verbose: int = 0
    no_color: bool = False
    console: Console | None = None

    def __post_init__(self) -> None:
        if self.console is None:
            self.console = Console(no_color=self.no_color, highlight=False)

    @property
    def is_json(self) -> bool:
        return self.fmt == OutputFormat.JSON

    def emit_json(self, data) -> None:
        if orjson is not None:
            sys.stdout.write(orjson.dumps(data, option=orjson.OPT_INDENT_2).decode("utf-8") + "\n")
        else:
            sys.stdout.write(_json.dumps(data, indent=2, default=str) + "\n")

    def print(self, *args, **kwargs) -> None:
        if self.quiet:
            return
        self.console.print(*args, **kwargs)

    def error(self, message: str) -> None:
        self.console.print(f"[bold red]Error:[/bold red] {message}", style="red")

    def warn(self, message: str) -> None:
        if not self.quiet:
            self.console.print(f"[yellow]Warning:[/yellow] {message}")

    def info(self, message: str, level: int = 1) -> None:
        if self.verbose >= level and not self.quiet:
            self.console.print(f"[dim]{message}[/dim]")


def render_table(
    ctx: OutputContext,
    title: str,
    columns: list[str],
    rows: list[list],
    json_key: str | None = None,
) -> None:
    """Render `rows` as a Rich table, a JSON array, or a markdown table."""
    if ctx.fmt == OutputFormat.JSON:
        payload = [dict(zip(columns, row)) for row in rows]
        ctx.emit_json({json_key: payload} if json_key else payload)
        return

    if ctx.fmt == OutputFormat.MARKDOWN:
        lines = [f"| {' | '.join(columns)} |", f"| {' | '.join(['---'] * len(columns))} |"]
        for row in rows:
            lines.append(f"| {' | '.join(str(c) for c in row)} |")
        print("\n".join(lines))
        return

    table = Table(title=title, show_lines=False)
    for col in columns:
        table.add_column(col)
    for row in rows:
        table.add_row(*[str(c) for c in row])
    ctx.print(table)


def render_kv(ctx: OutputContext, title: str, data: dict) -> None:
    """Render a flat key/value mapping — used for `project show`, `stats` summaries, etc."""
    if ctx.fmt == OutputFormat.JSON:
        ctx.emit_json(data)
        return
    if ctx.fmt == OutputFormat.MARKDOWN:
        lines = [f"## {title}", ""]
        for k, v in data.items():
            lines.append(f"- **{k}**: {v}")
        print("\n".join(lines))
        return
    table = Table(title=title, show_header=False)
    table.add_column("key", style="bold cyan")
    table.add_column("value")
    for k, v in data.items():
        table.add_row(str(k), str(v))
    ctx.print(table)
