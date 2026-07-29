"""`devtools dupes` — duplicate detection (proposal #12). Exact whole-file
duplicates by default (delegates to `stats_engine.find_duplicate_files`,
already used internally by `doctor`); `--code` switches to near-duplicate
*code block* detection via token-shingling (`core/dupes_engine.py`)."""

from __future__ import annotations

from typing import List, Optional

import typer

from devtools.commands._shared import build_ignore_rules, resolve_project
from devtools.core.dupes_engine import find_code_duplicates
from devtools.core.exit_codes import CHECK_FAILED
from devtools.core.export_engine import cache_output
from devtools.core.output import render_table
from devtools.core.stats_engine import find_duplicate_files
from devtools.utils.console import OutputContext

app = typer.Typer()


@app.command()
def dupes(
    ctx: typer.Context,
    project: Optional[str] = typer.Argument(None, help="Project to scan."),
    code: bool = typer.Option(
        False, "--code", help="Detect near-duplicate code blocks (token-shingling) instead of exact whole-file duplicates."
    ),
    min_lines: int = typer.Option(6, "--min-lines", help="Minimum consecutive non-blank lines per duplicate block (--code mode only)."),
    language: List[str] = typer.Option([], "--lang", help="Limit --code mode to specific language(s), e.g. python (repeatable)."),
    ci: bool = typer.Option(False, "--ci", help="Exit 5 if any duplicates are found."),
) -> None:
    """Find duplicate files (exact content match) or, with --code,
    near-duplicate code blocks that may be worth extracting/deduplicating."""
    state = ctx.obj
    proj = resolve_project(ctx, project)
    rules = build_ignore_rules(ctx, proj)

    if code:
        groups = find_code_duplicates(proj.resolved_path, rules, min_lines=min_lines, languages=language or None)
        _render_code_dupes(state.output, proj.name, groups, min_lines)
        if ci and groups:
            state.exit_code = CHECK_FAILED
            raise typer.Exit(code=CHECK_FAILED)
        return

    dup_files = find_duplicate_files(proj.resolved_path, rules)
    _render_file_dupes(state.output, proj.name, dup_files)
    if ci and dup_files:
        state.exit_code = CHECK_FAILED
        raise typer.Exit(code=CHECK_FAILED)


def _render_file_dupes(output: OutputContext, project_name: str, dup_files: dict) -> None:
    if output.is_json:
        payload = {"duplicate_files": [{"hash": h, "paths": paths} for h, paths in dup_files.items()]}
        output.emit_json(payload)
        cache_output("dupes", project_name, payload)
        return

    if not dup_files:
        output.print(f"[green]No duplicate files found in '{project_name}'.[/green]")
    else:
        rows = [[", ".join(paths), len(paths)] for paths in dup_files.values()]
        render_table(output, f"{project_name} — duplicate files", ["paths", "count"], rows)
    cache_output(
        "dupes", project_name, {"duplicate_files": [{"paths": paths} for paths in dup_files.values()]}
    )


def _render_code_dupes(output: OutputContext, project_name: str, groups: list, min_lines: int) -> None:
    if output.is_json:
        payload = {
            "min_lines": min_lines,
            "duplicate_blocks": [
                {
                    "lines": g.lines,
                    "occurrences": [
                        {"file": o.rel_path, "start_line": o.start_line, "end_line": o.end_line} for o in g.occurrences
                    ],
                }
                for g in groups
            ],
        }
        output.emit_json(payload)
        cache_output("dupes", project_name, payload)
        return

    if not groups:
        output.print(f"[green]No duplicate code blocks (>= {min_lines} lines) found in '{project_name}'.[/green]")
    else:
        rows = []
        for g in groups:
            locations = "; ".join(f"{o.rel_path}:{o.start_line}-{o.end_line}" for o in g.occurrences)
            rows.append([g.lines, len(g.occurrences), locations])
        render_table(output, f"{project_name} — duplicate code blocks", ["lines", "occurrences", "locations"], rows)
    cache_output(
        "dupes",
        project_name,
        {"duplicate_blocks": [{"lines": g.lines, "count": len(g.occurrences)} for g in groups]},
    )