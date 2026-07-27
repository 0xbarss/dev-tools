"""`devtools collect` — collect source files into one AI-ready file (spec §6)."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import typer

from devtools.commands._shared import build_ignore_rules, fail, resolve_project
from devtools.core import config as cfgmod
from devtools.core.collector import (
    chunk_by_tokens,
    collect_files,
    render_json,
    render_markdown,
    render_text,
)
from devtools.core.exit_codes import FILESYSTEM_ERROR, GENERAL_ERROR, INVALID_USAGE
from devtools.core.export_engine import cache_output
from devtools.utils.git import GitError, changed_files_since
from devtools.utils.helpers import ParseError, parse_size, utc_now_iso

app = typer.Typer()


@app.command()
def collect(
    ctx: typer.Context,
    project: Optional[str] = typer.Argument(None, help="Project to collect (defaults per global --project resolution)."),
    lang: List[str] = typer.Option([], "--lang", help="Restrict to these languages (repeatable)."),
    exclude: List[str] = typer.Option([], "--exclude", help="Extra glob(s) to exclude, added to config ignores (repeatable)."),
    max_size: Optional[str] = typer.Option(None, "--max-size", help="Skip files larger than this, e.g. 5MB."),
    fmt: str = typer.Option("markdown", "--format", help="Output content format: markdown, json, or text."),
    chunk_size: Optional[int] = typer.Option(None, "--chunk-size", help="Split output into numbered files if this token count is exceeded."),
    since: Optional[str] = typer.Option(None, "--since", help="Only collect files changed since this git ref."),
    no_gitignore: bool = typer.Option(False, "--no-gitignore", help="Don't respect the project's .gitignore."),
    out: Optional[Path] = typer.Option(None, "--out", help="Output directory (default: current directory)."),
    stdout: bool = typer.Option(False, "--stdout", help="Print to stdout instead of writing a file."),
) -> None:
    """Collect source files from a project into one (or several) AI-ready file(s)."""
    state = ctx.obj
    if fmt not in ("markdown", "json", "text"):
        fail(ctx, INVALID_USAGE, "--format must be one of: markdown, json, text")

    proj = resolve_project(ctx, project)
    max_size_bytes = None
    if max_size:
        try:
            max_size_bytes = parse_size(max_size)
        except ParseError as exc:
            fail(ctx, INVALID_USAGE, str(exc))

    rules = build_ignore_rules(ctx, proj, extra_excludes=list(exclude), use_gitignore=not no_gitignore)

    only_paths = None
    if since:
        try:
            only_paths = changed_files_since(proj.resolved_path, since)
        except GitError as exc:
            fail(ctx, GENERAL_ERROR, str(exc))

    result = collect_files(
        proj.resolved_path,
        rules,
        languages=list(lang) or None,
        max_size=max_size_bytes,
        only_paths=only_paths,
    )

    if state.output.is_json:
        payload = render_json(result)
        state.output.emit_json(payload)
        cache_output("collect", proj.name, payload)
        _touch_last_collected(proj.name)
        return

    if fmt == "json":
        content_groups = [_json_dump(render_json(result))]
        write_mode = "json"
    elif fmt == "text":
        content_groups = [render_text(result)]
        write_mode = "text"
    else:
        if chunk_size:
            chunks = chunk_by_tokens(result.files, chunk_size)
            content_groups = [
                render_markdown(_sub_result(result, chunk), proj.name, title=f"{proj.name} part {i+1}/{len(chunks)}")
                for i, chunk in enumerate(chunks)
            ]
        else:
            content_groups = [render_markdown(result, proj.name)]
        write_mode = "markdown"

    if stdout:
        for content in content_groups:
            print(content)
    else:
        out_dir = out or Path.cwd()
        out_dir.mkdir(parents=True, exist_ok=True)
        ext = {"markdown": "md", "json": "json", "text": "txt"}[write_mode]
        written = []
        for i, content in enumerate(content_groups):
            suffix = f"_{i+1}" if len(content_groups) > 1 else ""
            out_path = out_dir / f"{proj.name}_collect{suffix}.{ext}"
            try:
                out_path.write_text(content, encoding="utf-8")
            except OSError as exc:
                fail(ctx, FILESYSTEM_ERROR, f"Could not write {out_path}: {exc}")
            written.append(out_path)
        for p in written:
            state.output.print(f"[green]Wrote {p}[/green]")

    state.output.print(
        f"{len(result.files)} files, ~{result.total_tokens} tokens"
        + (" (truncated)" if result.truncated else "")
    )
    cache_output("collect", proj.name, render_json(result))
    _touch_last_collected(proj.name)


def _sub_result(result, files):
    from dataclasses import replace

    return replace(result, files=files)


def _json_dump(data) -> str:
    import json

    return json.dumps(data, indent=2, default=str)


def _touch_last_collected(project_name: str) -> None:
    projects = cfgmod.load_projects()
    if project_name in projects:
        projects[project_name].last_collected = utc_now_iso()
        cfgmod.save_projects(projects)