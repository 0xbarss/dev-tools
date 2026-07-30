"""`devtools docs` — AI-assisted doc generation (proposal §4, backlog #23).

Currently one subcommand, `generate`, which fills the same gap `doctor`
already detects (a missing README) but with drafted content instead of a
bare stub -- when AI is configured. Structured as its own `app` (like
`ci`, `notify`, `snapshot`) since "docs generate" reads naturally and
leaves room for a sibling like `docs check` later without renaming this one.
"""

from __future__ import annotations

from typing import Optional

import typer

from devtools.commands._shared import build_ignore_rules, fail, resolve_project
from devtools.core.docs_engine import generate_readme
from devtools.core.exit_codes import FILESYSTEM_ERROR, INVALID_USAGE
from devtools.core.llm_client import LLMClientError, get_client

app = typer.Typer(help="AI-assisted documentation generation.")


@app.command("generate")
def generate(
    ctx: typer.Context,
    project: Optional[str] = typer.Argument(None, help="Project to generate docs for."),
    write: bool = typer.Option(False, "--write", help="Write README.md instead of printing the draft to stdout."),
    force: bool = typer.Option(False, "--force", help="With --write, overwrite an existing README.md."),
) -> None:
    """Draft a README.md: real content if an AI provider is configured,
    otherwise the same stub template `doctor --fix` uses."""
    state = ctx.obj
    proj = resolve_project(ctx, project)
    rules = build_ignore_rules(ctx, proj)
    root = proj.resolved_path

    readme_path = root / "README.md"
    if write and readme_path.exists() and not force:
        fail(ctx, INVALID_USAGE, f"{readme_path} already exists. Use --force to overwrite, or omit --write to just preview.")
        return

    try:
        client = get_client(state.settings)
        content, ai_generated = generate_readme(root, rules, client, proj.name)
    except LLMClientError as exc:
        fail(ctx, INVALID_USAGE, str(exc))
        return

    if write:
        try:
            readme_path.write_text(content, encoding="utf-8")
        except OSError as exc:
            fail(ctx, FILESYSTEM_ERROR, f"Could not write {readme_path}: {exc}")
            return
        if state.output.is_json:
            state.output.emit_json({"path": str(readme_path), "ai_generated": ai_generated})
        else:
            source = "AI-drafted" if ai_generated else "stub template (no AI provider configured)"
            state.output.print(f"[green]Wrote {readme_path}[/green] ({source})")
        return

    if state.output.is_json:
        state.output.emit_json({"content": content, "ai_generated": ai_generated})
    else:
        if not ai_generated:
            state.output.warn("No AI provider configured — this is the stub template, not AI-drafted content.")
        print(content)
