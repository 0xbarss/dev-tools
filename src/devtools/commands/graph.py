"""`devtools graph` — internal module dependency graph (backlog #7/#29).
Stays thin per the existing `commands/` convention; all real logic lives
in `core/graph_engine.py`."""

from __future__ import annotations

from typing import Optional

import typer

from devtools.commands._shared import build_ignore_rules, resolve_project
from devtools.core.export_engine import cache_output
from devtools.core.graph_engine import build_dependency_graph
from devtools.core.output import render_table

app = typer.Typer()


@app.command()
def graph(
    ctx: typer.Context,
    project: Optional[str] = typer.Argument(None, help="Project to graph."),
    fmt: str = typer.Option("mermaid", "--format", help="Output shape: mermaid or dot."),
    module: Optional[str] = typer.Option(None, "--module", help="Only show this module/package and its internal edges, e.g. devtools.core."),
    top: int = typer.Option(15, "--top", help="How many modules to list by fan-in, in table view."),
) -> None:
    """Draw the project's internal Python import graph (Mermaid or DOT) --
    "who actually depends on whom" as a diagram, not a manifest listing."""
    state = ctx.obj
    proj = resolve_project(ctx, project)
    rules = build_ignore_rules(ctx, proj)

    if fmt not in ("mermaid", "dot"):
        state.output.warn("--format must be 'mermaid' or 'dot'; defaulting to 'mermaid'.")
        fmt = "mermaid"

    dep_graph = build_dependency_graph(proj.resolved_path, rules, module_prefix=module)
    rendered = dep_graph.to_mermaid() if fmt == "mermaid" else dep_graph.to_dot()
    fan_in = dep_graph.fan_in()

    if state.output.is_json:
        payload = {
            "format": fmt,
            "nodes": dep_graph.nodes,
            "edges": [{"source": e.source, "target": e.target} for e in dep_graph.edges],
            "rendered": rendered,
        }
        state.output.emit_json(payload)
        cache_output("graph", proj.name, payload)
        return

    if not dep_graph.nodes:
        state.output.print(f"[dim]No Python modules found in '{proj.name}'{f' under {module!r}' if module else ''}.[/dim]")
        return

    state.output.print(f"[bold]{proj.name} — dependency graph[/bold] ({len(dep_graph.nodes)} modules, {len(dep_graph.edges)} internal imports)")
    state.output.print(f"```{fmt}\n{rendered}\n```")

    ranked = sorted(fan_in.items(), key=lambda kv: kv[1], reverse=True)[:top]
    if any(count > 0 for _, count in ranked):
        render_table(
            state.output,
            f"Most depended-on modules (top {len(ranked)})",
            ["module", "fan-in (imported by N others)"],
            [[name, count] for name, count in ranked],
        )

    cache_output(
        "graph",
        proj.name,
        {"nodes": dep_graph.nodes, "edges": [{"source": e.source, "target": e.target} for e in dep_graph.edges]},
    )