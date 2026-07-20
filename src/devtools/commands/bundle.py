"""`devtools bundle` — an AI-ready repository snapshot (spec §6).

Bundles: tree, README, dependency manifests, config files, entry points, and
a curated set of "important" source files (heuristic: entry points, files
with the most inbound imports, common names like main/app/index/settings).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import typer

from devtools.commands._shared import build_ignore_rules, fail, resolve_project
from devtools.core.collector import collect_files, render_markdown
from devtools.core.deps_engine import detect_manifests
from devtools.core.exit_codes import FILESYSTEM_ERROR
from devtools.core.export_engine import cache_output
from devtools.core.scanner import scan_project
from devtools.core.tokenizer import count_tokens
from devtools.core.tree_engine import build_tree, render_markdown as tree_render_markdown

app = typer.Typer()

IMPORTANT_NAME_HINTS = {"main", "app", "index", "settings", "config", "server", "cli", "__init__"}
README_NAMES = {"readme.md", "readme", "readme.rst", "readme.txt"}
CONFIG_NAMES = {
    "pyproject.toml", "package.json", "cargo.toml", "go.mod", "pom.xml",
    "build.gradle", "build.gradle.kts", "pubspec.yaml", "tsconfig.json",
    "dockerfile", "docker-compose.yml", "docker-compose.yaml", ".env.example",
}

_IMPORT_RE = re.compile(
    r"^\s*(?:from\s+([.\w]+)\s+import|import\s+([.\w]+))"
    r"|^\s*(?:import|require)\s*\(?['\"]([./\w-]+)['\"]",
    re.MULTILINE,
)


@app.command()
def bundle(
    ctx: typer.Context,
    project: Optional[str] = typer.Argument(None, help="Project to bundle."),
    include_tests: bool = typer.Option(False, "--include-tests", help="Include test files in the curated source set."),
    max_tokens: int = typer.Option(100_000, "--max-tokens", help="Drop lower-priority files to stay under this token budget."),
    out: Optional[Path] = typer.Option(None, "--out", help="Output file path (default: <project>_bundle.md in cwd)."),
    stdout: bool = typer.Option(False, "--stdout", help="Print to stdout instead of writing a file."),
) -> None:
    """Produce <project>_bundle.md: tree + manifests + curated important source files."""
    state = ctx.obj
    proj = resolve_project(ctx, project)
    root = proj.resolved_path
    rules = build_ignore_rules(ctx, proj)

    all_files = list(scan_project(root, rules))
    inbound_counts = _count_inbound_references(all_files)

    def priority(entry) -> int:
        name = entry.path.stem.lower()
        score = 0
        if name in IMPORTANT_NAME_HINTS:
            score += 50
        if entry.rel_path.lower() in README_NAMES or entry.path.name.lower() in README_NAMES:
            score += 100
        if entry.path.name.lower() in CONFIG_NAMES:
            score += 80
        if not include_tests and ("test" in entry.rel_path.lower() or "spec" in entry.rel_path.lower()):
            score -= 1000
        score += inbound_counts.get(entry.path.stem, 0) * 5
        return score

    ranked = sorted(all_files, key=priority, reverse=True)

    selected_paths = []
    running_tokens = 0
    omitted = []
    for entry in ranked:
        p = priority(entry)
        if p <= -1000:
            continue
        try:
            text = entry.path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        tokens = count_tokens(text)
        if running_tokens + tokens > max_tokens:
            omitted.append(entry.rel_path)
            continue
        running_tokens += tokens
        selected_paths.append(entry.path)

    tree_node = build_tree(root, rules, max_depth=4)
    tree_md = tree_render_markdown(tree_node)
    manifests = [m.name for m in detect_manifests(root)]

    result = collect_files(root, rules, only_paths=selected_paths)
    body = render_markdown(result, proj.name, title=f"{proj.name} repository bundle")

    parts = [
        f"# {proj.name} repository bundle",
        "",
        "## Directory tree",
        "",
        tree_md,
        "",
        f"## Dependency manifests found: {', '.join(manifests) if manifests else 'none'}",
        "",
        body,
    ]
    if omitted:
        parts.append("## Truncated (exceeded --max-tokens)")
        parts.extend(f"- {p}" for p in omitted)

    content = "\n".join(parts)

    if stdout:
        print(content)
    else:
        out_path = out or (Path.cwd() / f"{proj.name}_bundle.md")
        try:
            out_path.write_text(content, encoding="utf-8")
        except OSError as exc:
            fail(ctx, FILESYSTEM_ERROR, f"Could not write {out_path}: {exc}")
        state.output.print(f"[green]Wrote {out_path}[/green]")

    state.output.print(
        f"{len(selected_paths)} files bundled, ~{running_tokens} tokens" + (" (truncated)" if omitted else "")
    )
    cache_output("bundle", proj.name, {"file_count": len(selected_paths), "tokens": running_tokens, "omitted": omitted})


def _count_inbound_references(entries) -> dict[str, int]:
    """Very rough "most inbound imports" heuristic: count how often each
    file's stem name appears as an import/require target across the project.
    """
    counts: dict[str, int] = {}
    stems = {e.path.stem for e in entries}
    for entry in entries:
        try:
            text = entry.path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for match in _IMPORT_RE.finditer(text):
            target = next((g for g in match.groups() if g), "")
            leaf = target.rsplit(".", 1)[-1].rsplit("/", 1)[-1]
            if leaf in stems:
                counts[leaf] = counts.get(leaf, 0) + 1
    return counts
