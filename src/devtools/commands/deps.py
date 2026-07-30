"""`devtools deps` — dependency analysis for Python, Node, Rust, Go, Java, Flutter (spec §6).

Reads local lockfiles/manifests only; `--outdated` is the one path that may
reach a package registry, and is opt-in per invocation via --allow-network
if allow_network=false in config (spec §6 `deps`).
"""

from __future__ import annotations

from typing import Optional

import typer

from devtools.commands._shared import fail, resolve_project
from devtools.core.deps_engine import analyze
from devtools.core.exit_codes import CHECK_FAILED, INVALID_USAGE
from devtools.core.export_engine import cache_output
from devtools.core.notify_engine import load_targets, send_notification
from devtools.core.output import render_table

app = typer.Typer()


@app.command()
def deps(
    ctx: typer.Context,
    project: Optional[str] = typer.Argument(None, help="Project to analyze."),
    graph: bool = typer.Option(False, "--graph", help="Show a per-ecosystem dependency count instead of a flat list."),
    outdated: bool = typer.Option(False, "--outdated", help="Check the configured registry for newer versions (network)."),
    check: bool = typer.Option(False, "--check", help="Exit 5 if any ecosystem has zero resolvable versions (CI use)."),
    allow_network: bool = typer.Option(False, "--allow-network", help="Permit this invocation to reach a package registry for --outdated."),
    notify: Optional[str] = typer.Option(None, "--notify", help="Send a summary to this configured `devtools notify` target, but only on failure (manifests found but nothing parsed)."),
) -> None:
    """Analyze dependency manifests found in the project."""
    state = ctx.obj
    proj = resolve_project(ctx, project)
    report = analyze(proj.resolved_path)

    if outdated:
        if not (allow_network or state.settings.allow_network):
            fail(
                ctx,
                INVALID_USAGE,
                "--outdated reaches a package registry. Pass --allow-network for this run, "
                "or set allow_network = true in config.toml.",
            )
        state.output.warn("--outdated network lookups are not implemented in this environment; showing local manifest data only.")

    if state.output.is_json:
        payload = {
            "ecosystems": report.ecosystems_found,
            "manifest_files": report.manifest_files,
            "dependencies": [
                {"name": d.name, "version": d.version, "ecosystem": d.ecosystem, "dev": d.dev, "source": d.source_file}
                for d in report.dependencies
            ],
        }
        state.output.emit_json(payload)
        cache_output("deps", proj.name, payload)
    else:
        if not report.dependencies:
            state.output.print(f"No recognized dependency manifests found in '{proj.name}'.")
        elif graph:
            by_eco = report.by_ecosystem()
            rows = [[eco, len(deps_)] for eco, deps_ in sorted(by_eco.items(), key=lambda kv: -len(kv[1]))]
            render_table(state.output, f"{proj.name} — dependency graph", ["ecosystem", "count"], rows)
        else:
            rows = [[d.ecosystem, d.name, d.version or "*", "dev" if d.dev else ""] for d in report.dependencies]
            render_table(state.output, f"{proj.name} — dependencies", ["ecosystem", "name", "version", "kind"], rows)
        cache_output(
            "deps",
            proj.name,
            {"ecosystems": report.ecosystems_found, "dependency_count": len(report.dependencies)},
        )

    is_failure = not report.dependencies and report.manifest_files

    if notify is not None and is_failure:
        targets = load_targets()
        target = targets.get(notify)
        if target is None:
            fail(ctx, INVALID_USAGE, f"No notification target named '{notify}'. Run `devtools notify list`.")
        send_notification(
            target,
            event="devtools deps",
            message=f"deps found {len(report.manifest_files)} manifest(s) in '{proj.name}' but could not parse any dependencies.",
            fields={"project": proj.name, "manifest_files": report.manifest_files},
        )

    if check and is_failure:
        state.output.error("Manifests were found but no dependencies could be parsed from them.")
        state.exit_code = CHECK_FAILED
        raise typer.Exit(code=CHECK_FAILED)
