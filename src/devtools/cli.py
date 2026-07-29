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
from typer.core import TyperGroup

from devtools import __version__
from devtools.commands import (
    alias as alias_cmd,
    branches as branches_cmd,
    bundle as bundle_cmd,
    changelog as changelog_cmd,
    ci as ci_cmd,
    clean as clean_cmd,
    collect as collect_cmd,
    completion as completion_cmd,
    complexity as complexity_cmd,
    compliance as compliance_cmd,
    config as config_cmd,
    context as context_cmd,
    deadcode as deadcode_cmd,
    deps as deps_cmd,
    doctor as doctor_cmd,
    dupes as dupes_cmd,
    explain as explain_cmd,
    export as export_cmd,
    graph as graph_cmd,
    grep as grep_cmd,
    health as health_cmd,
    history as history_cmd,
    ignore as ignore_cmd,
    index as index_cmd,
    init as init_cmd,
    investigate as investigate_cmd,
    license_check as license_check_cmd,
    lint as lint_cmd,
    marketplace as marketplace_cmd,
    mcp_serve as mcp_serve_cmd,
    notify as notify_cmd,
    owners as owners_cmd,
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

# Click's Group stops parsing group-level options at the first non-option
# token (the subcommand name); anything after that belongs to the
# subcommand's own parser. That's the standard, unambiguous behavior for
# flags a subcommand might redefine with different semantics (e.g. `history
# --project` filters by project, `collect --format` picks a *content*
# format -- both distinct from the global `--project`/`--format`). But a
# handful of global flags are never redefined by any command and are
# harmless/expected to work no matter where they appear on the command
# line (`devtools grep foo --json` reads just as naturally as `devtools
# --json grep foo`). This Group subclass reorders *only* that safe subset
# ahead of the subcommand before Click's normal parsing runs; every other
# flag keeps Click's standard "must precede the subcommand" behavior.
_REORDERABLE_NO_VALUE_FLAGS = {"--json", "--quiet", "-q", "--no-color", "--verbose", "-v"}


class _GlobalFlagReorderingGroup(TyperGroup):
    def parse_args(self, ctx: typer.Context, args: list[str]) -> list[str]:
        front: list[str] = []
        rest: list[str] = []
        stop_reordering = False
        for token in args:
            if stop_reordering:
                rest.append(token)
                continue
            if token == "--":
                stop_reordering = True
                rest.append(token)
                continue
            if token in _REORDERABLE_NO_VALUE_FLAGS:
                front.append(token)
            else:
                rest.append(token)
        return super().parse_args(ctx, front + rest)


app = typer.Typer(
    name="devtools",
    help="A personal, installable developer toolkit for AI-assisted repository workflows.",
    no_args_is_help=True,
    add_completion=False,  # `devtools completion install <shell>` handles this explicitly
    cls=_GlobalFlagReorderingGroup,
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
app.command("deadcode")(deadcode_cmd.deadcode)
app.command("dupes")(dupes_cmd.dupes)
app.command("complexity")(complexity_cmd.complexity)
app.command("investigate")(investigate_cmd.investigate)
app.command("owners")(owners_cmd.owners)
app.command("branches")(branches_cmd.branches)
app.command("health")(health_cmd.health)
app.command("graph")(graph_cmd.graph)

# --- sub-apps with their own subcommands -----------------------------------------
app.add_typer(project_cmd.app, name="project")
app.add_typer(ignore_cmd.app, name="ignore")
app.add_typer(alias_cmd.app, name="alias")
app.add_typer(completion_cmd.app, name="completion")
app.add_typer(ci_cmd.app, name="ci")
app.add_typer(config_cmd.app, name="config")
app.add_typer(index_cmd.app, name="index")
app.add_typer(notify_cmd.app, name="notify")
app.add_typer(compliance_cmd.app, name="compliance")
app.add_typer(marketplace_cmd.app, name="marketplace")


if __name__ == "__main__":
    app()
