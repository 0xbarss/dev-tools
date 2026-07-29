"""`devtools sbom` — software bill of materials from local manifests.

Reads only local manifests via `deps_engine` (same six ecosystems `deps`
already supports) — no registry calls, consistent with the project's
no-required-network default.
"""

from __future__ import annotations

from typing import Optional

import typer

from devtools.commands._shared import resolve_project
from devtools.core.export_engine import cache_output
from devtools.core.sbom_engine import build_cyclonedx_sbom

app = typer.Typer()


@app.command()
def sbom(
    ctx: typer.Context,
    project: Optional[str] = typer.Argument(None, help="Project to generate an SBOM for."),
    format: str = typer.Option("cyclonedx", "--format", help="Output format: 'cyclonedx' (default) is the only shape emitted; --json controls raw vs. pretty-printed emission."),
) -> None:
    """Generate a CycloneDX-shaped software bill of materials from local dependency manifests."""
    state = ctx.obj
    proj = resolve_project(ctx, project)

    if format != "cyclonedx":
        state.output.warn(f"Unknown --format {format!r}; emitting CycloneDX (the only supported shape).")

    bom = build_cyclonedx_sbom(proj.resolved_path)

    if state.output.is_json:
        state.output.emit_json(bom)
    elif not state.output.quiet:
        import json as _json

        print(_json.dumps(bom, indent=2))

    cache_output("sbom", proj.name, {"component_count": len(bom["components"])})