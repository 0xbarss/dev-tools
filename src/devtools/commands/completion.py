"""`devtools completion` — standard Typer-provided shell completion install
for bash/zsh/fish (spec §7).
"""

from __future__ import annotations

import typer
from typer.main import get_command

app = typer.Typer(help="Install or show shell completion for devtools.")

_SUPPORTED_SHELLS = ("bash", "zsh", "fish")


@app.command("install")
def install(ctx: typer.Context, shell: str = typer.Argument(..., help="One of: bash, zsh, fish.")) -> None:
    """Install shell completion for devtools into your shell's config."""
    state = ctx.obj
    if shell not in _SUPPORTED_SHELLS:
        state.output.error(f"Unsupported shell '{shell}'. Choose one of: {', '.join(_SUPPORTED_SHELLS)}")
        raise typer.Exit(code=2)

    # Typer/Click's built-in installer handles writing the right completion
    # script into the user's shell config for us.
    from click.shell_completion import get_completion_class

    completion_cls = get_completion_class(shell)
    if completion_cls is None:
        state.output.error(f"click has no completion support for '{shell}' in this installation.")
        raise typer.Exit(code=1)

    import os

    root_cmd = get_command(_root_app())
    completion_cls(cli=root_cmd, ctx_args={}, prog_name="devtools", complete_var="_DEVTOOLS_COMPLETE").install()
    state.output.print(f"[green]Installed {shell} completion for devtools. Restart your shell to pick it up.[/green]")


@app.command("show")
def show(ctx: typer.Context, shell: str = typer.Argument(..., help="One of: bash, zsh, fish.")) -> None:
    """Print the completion script for `shell` instead of installing it."""
    state = ctx.obj
    if shell not in _SUPPORTED_SHELLS:
        state.output.error(f"Unsupported shell '{shell}'. Choose one of: {', '.join(_SUPPORTED_SHELLS)}")
        raise typer.Exit(code=2)

    from click.shell_completion import get_completion_class

    completion_cls = get_completion_class(shell)
    root_cmd = get_command(_root_app())
    script = completion_cls(cli=root_cmd, ctx_args={}, prog_name="devtools", complete_var="_DEVTOOLS_COMPLETE").source()
    print(script)


def _root_app():
    from devtools.cli import app as root_app

    return root_app