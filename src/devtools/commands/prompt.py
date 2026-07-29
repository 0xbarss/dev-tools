"""`devtools prompt` — a library of reusable AI prompt templates
(Prioritized Backlog: "Prompt template library", P3).

`prompt run` renders the template and prints it by default, so it's useful
even with `ai_provider = "none"` (paste the rendered prompt into whatever AI
tool you like). Pass `--complete` to also send it through the configured
LLM client, matching how `explain`/`context` degrade gracefully without one.
"""

from __future__ import annotations

import typer

from devtools.commands._shared import fail
from devtools.core.exit_codes import GENERAL_ERROR, INVALID_USAGE, PROJECT_NOT_FOUND
from devtools.core.output import render_table
from devtools.core.prompt_store import (
    PromptRenderError,
    add_template,
    load_templates,
    parse_var_options,
    remove_template,
    render_template,
)

app = typer.Typer(help="A library of reusable AI prompt templates.")


@app.command("add")
def add(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Short name for this template, e.g. 'pr-summary'."),
    template: str = typer.Argument(..., help="Template text; use {variable} placeholders, e.g. 'Summarize {diff} in one paragraph.'"),
    description: str = typer.Option("", "--description", help="Optional description shown in `prompt list`."),
) -> None:
    """Save a prompt template."""
    state = ctx.obj
    add_template(name, template, description=description)
    state.output.print(f"[green]Saved prompt template '{name}'[/green]")


@app.command("list")
def list_templates(ctx: typer.Context) -> None:
    """List all saved prompt templates."""
    state = ctx.obj
    templates = load_templates()
    rows = [[t.name, ", ".join(t.variables) or "-", t.description] for t in sorted(templates.values(), key=lambda t: t.name)]
    render_table(state.output, "Prompt templates", ["name", "variables", "description"], rows, json_key="templates")


@app.command("show")
def show(ctx: typer.Context, name: str = typer.Argument(...)) -> None:
    """Print a saved template's raw text."""
    state = ctx.obj
    template = load_templates().get(name)
    if template is None:
        fail(ctx, PROJECT_NOT_FOUND, f"No prompt template named '{name}'. Run `devtools prompt list` to see saved templates.")
    if state.output.is_json:
        state.output.emit_json({"name": template.name, "template": template.template, "variables": template.variables, "description": template.description})
    else:
        print(template.template)


@app.command("run")
def run(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    var: list[str] = typer.Option([], "--var", help="Fill a template variable: --var key=value (repeatable)."),
    complete: bool = typer.Option(False, "--complete", help="Also send the rendered prompt through the configured AI provider."),
) -> None:
    """Render a saved template (and optionally run it through the AI provider)."""
    state = ctx.obj
    template = load_templates().get(name)
    if template is None:
        fail(ctx, PROJECT_NOT_FOUND, f"No prompt template named '{name}'. Run `devtools prompt list` to see saved templates.")

    try:
        variables = parse_var_options(var)
        rendered = render_template(template, variables)
    except (ValueError, PromptRenderError) as exc:
        fail(ctx, INVALID_USAGE, str(exc))

    if not complete:
        if state.output.is_json:
            state.output.emit_json({"name": name, "rendered": rendered})
        else:
            print(rendered)
        return

    from devtools.core.llm_client import LLMClientError, get_client

    try:
        client = get_client(state.settings)
        response = client.complete(rendered)
    except LLMClientError as exc:
        fail(ctx, GENERAL_ERROR, str(exc))
        return

    if state.output.is_json:
        state.output.emit_json({"name": name, "rendered": rendered, "response": response})
    else:
        print(response)


@app.command("remove")
def remove(ctx: typer.Context, name: str = typer.Argument(...)) -> None:
    """Delete a saved prompt template."""
    state = ctx.obj
    if remove_template(name):
        state.output.print(f"Removed prompt template '{name}'")
    else:
        fail(ctx, PROJECT_NOT_FOUND, f"No prompt template named '{name}'.")
