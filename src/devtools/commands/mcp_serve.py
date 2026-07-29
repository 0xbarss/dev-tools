"""`devtools mcp-serve` — MCP server mode (proposal backlog #24, P0).

Exposes the same `core/` engines every CLI command already uses as MCP
tools, so Claude Code or any other MCP-speaking agent can call `devtools`
functionality directly instead of shelling out to the CLI and parsing text.
No command-layer duplication: every tool function below is a thin wrapper
around an existing `core/*_engine.py` call.

The `mcp` SDK is an optional dependency (`pip install "devtools[mcp]"`) --
importing it lazily here means the core `devtools` install never requires it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from devtools.core import config as cfgmod
from devtools.core import deps_engine, doctor_checks, index_engine
from devtools.core.changelog_engine import generate_changelog, render_markdown as render_changelog_markdown
from devtools.core.collector import collect_files, render_markdown as render_collect_markdown
from devtools.core.explain_engine import explain as explain_engine
from devtools.core.grep_engine import grep as grep_engine
from devtools.core.ignore_rules import IgnoreRules
from devtools.core.lint_engine import run_lint
from devtools.core.llm_client import LLMClientError, get_client
from devtools.core.search_engine import search as search_engine, semantic_search
from devtools.core.stats_engine import compute_stats
from devtools.core.tree_engine import build_tree, to_dict
from devtools.models.project import Project
from devtools.utils.git import GitError

app = typer.Typer()

_MCP_INSTALL_HINT = (
    "The `mcp` package is required for mcp-serve. Install it with `pip install \"devtools[mcp]\"` "
    "(or `pip install mcp`), then re-run `devtools mcp-serve`."
)


def _rules_for(project: Project) -> IgnoreRules:
    settings = cfgmod.load_settings(None)
    ignored_dirs = settings.ignored_dirs_for(project.name)
    return IgnoreRules.build(root=project.resolved_path, base_ignored_dirs=ignored_dirs)


def _resolve(projects: dict[str, Project], name: str) -> Project:
    project = projects.get(name)
    if project is None:
        raise ValueError(f"Project '{name}' is not registered. Run `devtools project add {name} <path>` first.")
    if not project.exists():
        raise ValueError(f"Project '{name}' path does not exist: {project.path}")
    return project


def build_server():
    """Construct the FastMCP server and register every tool. Split out from
    `mcp_serve()` so tests can build + introspect it without starting an
    actual (blocking) stdio server."""
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:  # pragma: no cover - exercised via CLI error path
        raise RuntimeError(_MCP_INSTALL_HINT) from exc

    server = FastMCP(
        name="devtools",
        instructions=(
            "Repository intelligence tools: stats, tree, doctor (health checks), deps "
            "(dependency analysis), grep, search (keyword or --semantic), lint, context "
            "(task-scoped code retrieval), explain (AI), and changelog. All tools take a "
            "`project` argument matching a name registered via `devtools project add`."
        ),
    )
    projects = cfgmod.load_projects()

    @server.tool()
    def list_projects() -> list[dict]:
        """List every project registered with devtools (name + path)."""
        return [{"name": p.name, "path": p.path} for p in projects.values()]

    @server.tool()
    def stats(project: str) -> dict:
        """Repository statistics: file/line counts by language, size, tokens."""
        proj = _resolve(projects, project)
        rules = _rules_for(proj)
        report = compute_stats(proj.resolved_path, rules)
        return {
            "file_count": report.file_count,
            "total_lines": report.total_lines,
            "total_size": report.total_size,
            "total_tokens": report.total_tokens,
            "language_counts": dict(report.language_counts),
        }

    @server.tool()
    def tree(project: str, max_depth: Optional[int] = None, source_only: bool = False) -> dict:
        """File tree for a project, optionally depth-limited or source-only."""
        proj = _resolve(projects, project)
        rules = _rules_for(proj)
        node = build_tree(proj.resolved_path, rules, max_depth=max_depth, source_only=source_only)
        return to_dict(node)

    @server.tool()
    def doctor(project: str) -> dict:
        """Repository health checks: missing README/LICENSE/tests, binaries, duplicates, etc."""
        proj = _resolve(projects, project)
        rules = _rules_for(proj)
        settings = cfgmod.load_settings(None)
        issues = doctor_checks.run_all_checks(proj.resolved_path, rules, settings.ignored_dirs_for(proj.name))
        return {"issues": [{"check": i.check, "severity": i.severity, "message": i.message, "fixable": i.fixable} for i in issues]}

    @server.tool()
    def deps(project: str) -> dict:
        """Dependency analysis across Python/Node/Rust/Go/Java/Flutter manifests."""
        proj = _resolve(projects, project)
        report = deps_engine.analyze(proj.resolved_path)
        return {
            "ecosystems_found": report.ecosystems_found,
            "manifest_files": report.manifest_files,
            "dependencies": [
                {"name": d.name, "version": d.version, "ecosystem": d.ecosystem, "dev": d.dev} for d in report.dependencies
            ],
        }

    @server.tool()
    def grep(project: str, pattern: str, regex: bool = False, case_sensitive: bool = False) -> list[dict]:
        """Search file contents for a literal string or regex pattern."""
        proj = _resolve(projects, project)
        rules = _rules_for(proj)
        matches = grep_engine(proj.resolved_path, rules, pattern, regex=regex, case_sensitive=case_sensitive)
        return [{"path": m.rel_path, "line": m.line_number, "text": m.line} for m in matches]

    @server.tool()
    def search(project: str, concept: str, semantic: bool = False) -> dict:
        """Search by concept: keyword/synonym expansion (default) or --semantic
        (cosine similarity over the local TF-IDF index; run index build --vectors first)."""
        proj = _resolve(projects, project)
        rules = _rules_for(proj)
        used_semantic = False
        if semantic:
            hits, used_semantic = semantic_search(proj.resolved_path, proj.name, concept, ignore_rules=rules)
            if not used_semantic:
                hits = search_engine(proj.resolved_path, rules, concept)
        else:
            hits = search_engine(proj.resolved_path, rules, concept)
        return {
            "used_semantic": used_semantic,
            "hits": [{"path": h.rel_path, "score": h.score, "matched_terms": h.matched_terms} for h in hits],
        }

    @server.tool()
    def lint(project: str, ecosystem: Optional[str] = None) -> dict:
        """Run the right linter(s) per detected ecosystem and return normalized findings."""
        proj = _resolve(projects, project)
        report = run_lint(proj.resolved_path, only_ecosystems=[ecosystem] if ecosystem else None)
        return {
            "findings": [
                {"file": f.file, "line": f.line, "rule": f.rule, "severity": f.severity, "message": f.message, "source_linter": f.source_linter}
                for f in report.findings
            ],
            "skipped": [{"linter": r.linter, "error": r.error} for r in report.results if not r.ran],
        }

    @server.tool()
    def context(project: str, question: str, top: int = 8) -> dict:
        """Task-scoped code retrieval: the files most relevant to a natural-language question."""
        proj = _resolve(projects, project)
        rules = _rules_for(proj)
        hits = search_engine(proj.resolved_path, rules, question)[:top]
        paths = [proj.resolved_path / h.rel_path for h in hits]
        result = collect_files(proj.resolved_path, rules, only_paths=paths)
        return {
            "markdown": render_collect_markdown(result, proj.name, title=f"{proj.name} context: {question}"),
            "file_count": len(result.files),
            "total_tokens": result.total_tokens,
        }

    @server.tool()
    def explain(project: str, target: str) -> dict:
        """AI explanation of a file or symbol. Requires an ai_provider configured via
        `devtools config set ai_provider claude|openai|ollama`."""
        proj = _resolve(projects, project)
        rules = _rules_for(proj)
        settings = cfgmod.load_settings(None)
        try:
            client = get_client(settings)
            explanation = explain_engine(proj.resolved_path, rules, target, client)
        except (LLMClientError, ValueError) as exc:
            return {"error": str(exc)}
        return {"explanation": explanation}

    @server.tool()
    def changelog(project: str, since: Optional[str] = None, until: str = "HEAD") -> dict:
        """Generate a Keep-a-Changelog-style summary of commits since `since`."""
        proj = _resolve(projects, project)
        try:
            report = generate_changelog(proj.resolved_path, since=since, until=until)
        except GitError as exc:
            return {"error": str(exc)}
        return {"markdown": render_changelog_markdown(report, title=f"{proj.name} — Changelog")}

    return server


@app.command("mcp-serve")
def mcp_serve(
    ctx: typer.Context,
    transport: str = typer.Option("stdio", "--transport", help="stdio (default, for local agents like Claude Code), sse, or streamable-http."),
) -> None:
    """Run devtools as an MCP server, exposing stats/tree/doctor/deps/grep/search/
    lint/context/explain/changelog as MCP tools for Claude Code or other agents."""
    state = ctx.obj
    try:
        server = build_server()
    except RuntimeError as exc:
        state.output.error(str(exc))
        raise typer.Exit(code=1)
    server.run(transport=transport)  # type: ignore[arg-type]