"""`devtools tree` — better directory tree (spec §6)."""

from __future__ import annotations

from typing import Optional

import typer

from devtools.commands._shared import build_ignore_rules, resolve_project
from devtools.core.export_engine import cache_output
from devtools.core.output import OutputFormat
from devtools.core.tree_engine import build_tree, render_lines, render_markdown, to_dict

app = typer.Typer()


@app.command()
def tree(
    ctx: typer.Context,
    project: Optional[str] = typer.Argument(None, help="Project to show the tree for."),
    depth: Optional[int] = typer.Option(None, "--depth", help="Maximum depth to descend."),
    markdown: bool = typer.Option(False, "--markdown", help="Render as a fenced markdown code block."),
    source_only: bool = typer.Option(False, "--source-only", help="Hide non-code files."),
) -> None:
    """Render a directory tree for a project, respecting the shared ignore rules."""
    state = ctx.obj
    proj = resolve_project(ctx, project)
    rules = build_ignore_rules(ctx, proj)
    node = build_tree(proj.resolved_path, rules, max_depth=depth, source_only=source_only)

    if state.output.is_json:
        state.output.emit_json(to_dict(node))
        cache_output("tree", proj.name, to_dict(node))
        return

    if markdown or state.output.fmt == OutputFormat.MARKDOWN:
        print(render_markdown(node))
    else:
        for line in render_lines(node):
            state.output.print(line)

    cache_output("tree", proj.name, to_dict(node))