"""Typer app assembly and global options (spec §5).

Every command shares: --json, --quiet/-q, --verbose/-v (repeatable),
--no-color, --config PATH, --project NAME. This module wires the global
callback that builds the shared OutputContext + loads settings/projects
once, stores them on ctx.obj, and records the run to history.jsonl when
the whole invocation finishes.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

import typer

from devtools import __version__
from devtools.commands import (
    alias as alias_cmd,
    bundle as bundle_cmd,
    changelog as changelog_cmd,
    ci as ci_cmd,
    clean as clean_cmd,
    collect as collect_cmd,
    completion as completion_cmd,
    config as config_cmd,
    context as context_cmd,
    deps as deps_cmd,
    doctor as doctor_cmd,
    explain as explain_cmd,
    export as export_cmd,
    grep as grep_cmd,
    history as history_cmd,
    ignore as ignore_cmd,
    index as index_cmd,
    init as init_cmd,
    license_check as license_check_cmd,
    lint as lint_cmd,
    mcp_serve as mcp_serve_cmd,
    project as project_cmd,
    review as review_cmd,
    sbom as sbom_cmd,
    search as search_cmd,
    stats as stats_cmd,
    tree as tree_cmd,
    update as update_cmd,
)
from devtools.core import config as cfgmod
from devtools.core.exit_codes import SUCCESS
from devtools.core.history_log import record_run
from devtools.utils.console import build_output_context

app = typer.Typer(
    name="devtools",
    help="A personal, installable developer toolkit for AI-assisted repository workflows.",
    no_args_is_help=True,
    add_completion=False,  # `devtools completion install <shell>` handles this explicitly
)


class GlobalState:
    """Everything a command needs, resolved once in the root callback."""

    def __init__(self) -> None:
        self.output = None
        self.settings = None
        self.projects: dict = {}
        self.config_path: Optional[Path] = None
        self.project_arg: Optional[str] = None
        self.command_name: str = ""
        self.exit_code: int = SUCCESS


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"devtools {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    ctx: typer.Context,
    json: bool = typer.Option(False, "--json", help="Emit machine-readable JSON instead of Rich tables."),
    format: Optional[str] = typer.Option(None, "--format", help="Output format, e.g. markdown."),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress non-essential output; errors still print."),
    verbose: int = typer.Option(0, "--verbose", "-v", count=True, help="-v = info, -vv = debug."),
    no_color: bool = typer.Option(False, "--no-color", help="Disable ANSI colors (also respects NO_COLOR)."),
    config: Optional[Path] = typer.Option(None, "--config", help="Override the config file location for this invocation."),
    project: Optional[str] = typer.Option(None, "--project", help="Explicit project name for this invocation."),
    version: Optional[bool] = typer.Option(None, "--version", callback=_version_callback, is_eager=True, help="Show the devtools version and exit."),
) -> None:
    """devtools — a personal, installable developer toolkit."""
    # `init` bootstraps implicitly (and idempotently) so a fresh install
    # never hard-crashes on a missing config directory (spec §6 `init`).
    init_cmd.ensure_initialized()

    state = GlobalState()
    state.output = build_output_context(json=json, fmt=format, quiet=quiet, verbose=verbose, no_color=no_color)
    state.settings = cfgmod.load_settings(config)
    state.projects = cfgmod.load_projects()
    state.config_path = config
    state.project_arg = project
    state.command_name = ctx.invoked_subcommand or ""
    ctx.obj = state

    start = time.perf_counter()

    def _finalize() -> None:
        duration_ms = int((time.perf_counter() - start) * 1000)
        record_run(
            cmd=state.command_name or "unknown",
            project=state.project_arg,
            duration_ms=duration_ms,
            exit_code=state.exit_code,
        )

    ctx.call_on_close(_finalize)


# --- top-level single commands --------------------------------------------------
# Registered directly (not via add_typer) so they stay flat, e.g. `devtools
# collect api` rather than nesting as `devtools collect collect api`.
app.command("init")(init_cmd.init)
app.command("collect")(collect_cmd.collect)
app.command("bundle")(bundle_cmd.bundle)
app.command("context")(context_cmd.context)
app.command("grep")(grep_cmd.grep)
app.command("tree")(tree_cmd.tree)
app.command("stats")(stats_cmd.stats)
app.command("doctor")(doctor_cmd.doctor)
app.command("deps")(deps_cmd.deps)
app.command("clean")(clean_cmd.clean)
app.command("search")(search_cmd.search)
app.command("export")(export_cmd.export)
app.command("history")(history_cmd.history)
app.command("update")(update_cmd.update)
app.command("sbom")(sbom_cmd.sbom)
app.command("license-check")(license_check_cmd.license_check)
app.command("lint")(lint_cmd.lint)
app.command("changelog")(changelog_cmd.changelog)
app.command("explain")(explain_cmd.explain)
app.command("review")(review_cmd.review)
app.command("mcp-serve")(mcp_serve_cmd.mcp_serve)

# --- sub-apps with their own subcommands -----------------------------------------
app.add_typer(project_cmd.app, name="project")
app.add_typer(ignore_cmd.app, name="ignore")
app.add_typer(alias_cmd.app, name="alias")
app.add_typer(completion_cmd.app, name="completion")
app.add_typer(ci_cmd.app, name="ci")
app.add_typer(config_cmd.app, name="config")
app.add_typer(index_cmd.app, name="index")


if __name__ == "__main__":
    app()
