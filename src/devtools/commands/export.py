"""`devtools export` — turns any command's last output into a shareable file
format beyond markdown/json (spec §7), e.g. CSV for stats, HTML for tree.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from devtools.commands._shared import fail, resolve_project
from devtools.core.exit_codes import GENERAL_ERROR, INVALID_USAGE
from devtools.core.export_engine import load_cached_output, to_csv, to_html_table, to_sarif, tree_to_html

app = typer.Typer()

_TABULAR_LIST_KEYS = {"largest_files", "dependencies", "matches", "projects", "rules", "findings"}


@app.command()
def export(
    ctx: typer.Context,
    command: str = typer.Argument(..., help="Which command's cached output to export, e.g. stats, tree, deps, grep, lint."),
    project: Optional[str] = typer.Argument(None, help="Project whose cached output to export."),
    fmt: str = typer.Option(..., "--format", help="Target format: csv, html, or sarif (sarif is lint-only)."),
    out: Optional[Path] = typer.Option(None, "--out", help="Output file path (default: <project>_<command>.<ext> in cwd)."),
) -> None:
    """Convert a previously cached command output into CSV, HTML, or (for
    `lint`) SARIF -- e.g. for GitHub code scanning or another SARIF-reading
    dashboard."""
    state = ctx.obj
    proj = resolve_project(ctx, project)

    if fmt not in ("csv", "html", "sarif"):
        fail(ctx, INVALID_USAGE, "--format must be one of: csv, html, sarif")
    if fmt == "sarif" and command != "lint":
        fail(ctx, INVALID_USAGE, "--format sarif is only supported for `lint` output.")

    data = load_cached_output(command, proj.name)
    if data is None:
        fail(
            ctx,
            GENERAL_ERROR,
            f"No cached output found for `{command}` on '{proj.name}'. Run `devtools {command} {proj.name}` first.",
        )

    title = f"{proj.name} - {command}"

    if fmt == "sarif":
        findings = data.get("findings", []) if isinstance(data, dict) else []
        content = to_sarif(findings)
        ext = "sarif"
    elif command == "tree" and isinstance(data, dict) and data.get("type") == "dir":
        if fmt == "csv":
            fail(ctx, INVALID_USAGE, "`tree` output isn't tabular; only --format html is supported for it.")
        content = tree_to_html(title, data)
        ext = "html"
    else:
        rows = _extract_rows(data)
        if not rows:
            fail(ctx, GENERAL_ERROR, f"Cached `{command}` output for '{proj.name}' has no tabular data to export.")
        content = to_csv(rows) if fmt == "csv" else to_html_table(title, rows)
        ext = fmt

    out_path = out or (Path.cwd() / f"{proj.name}_{command}.{ext}")
    out_path.write_text(content, encoding="utf-8")
    state.output.print(f"[green]Wrote {out_path}[/green]")


def _extract_rows(data) -> list[dict]:
    if isinstance(data, list):
        return [d for d in data if isinstance(d, dict)]
    if isinstance(data, dict):
        for key in _TABULAR_LIST_KEYS:
            if key in data and isinstance(data[key], list):
                return [d for d in data[key] if isinstance(d, dict)]
        if "files" in data and isinstance(data["files"], list):
            return [d for d in data["files"] if isinstance(d, dict)]
    return []