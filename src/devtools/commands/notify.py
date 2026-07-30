"""`devtools notify` — configure and send Slack/Teams/Jira/generic webhook
notifications (Prioritized Backlog: "Enterprise notifications", P2).

Kept as its own command group rather than baked into `doctor`/`compliance`
directly, so any command can grow a `--notify <name>` flag later (compliance
does, as the first real consumer — see `commands/compliance.py`) without
duplicating webhook plumbing.
"""

from __future__ import annotations

from typing import List, Optional

import typer

from devtools.commands._shared import fail
from devtools.core.exit_codes import GENERAL_ERROR, INVALID_USAGE
from devtools.core.notify_engine import (
    NotifyError,
    add_target,
    load_targets,
    remove_target,
    send_notification,
)
from devtools.core.output import render_table

app = typer.Typer(help="Configure and send Slack/Teams/Jira/generic webhook notifications.")


def _parse_fields(raw_fields: List[str]) -> dict:
    fields = {}
    for item in raw_fields:
        if "=" not in item:
            raise NotifyError(f"--field values must be key=value, got {item!r}.")
        key, _, value = item.partition("=")
        fields[key.strip()] = value.strip()
    return fields


@app.command("add")
def add(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Name to save this notification target under."),
    webhook_url: str = typer.Argument(..., help="The provider's webhook URL."),
    kind: str = typer.Option("generic", "--kind", help="slack | teams | jira | generic"),
    project_key: Optional[str] = typer.Option(None, "--project-key", help="Jira project key (jira targets only)."),
    issue_type: Optional[str] = typer.Option(None, "--issue-type", help="Jira issue type (jira targets only)."),
) -> None:
    """Register a named webhook target."""
    state = ctx.obj
    extra = {}
    if project_key:
        extra["project_key"] = project_key
    if issue_type:
        extra["issue_type"] = issue_type
    try:
        add_target(name, kind, webhook_url, extra=extra)
    except NotifyError as exc:
        fail(ctx, INVALID_USAGE, str(exc))
    state.output.print(f"[green]Saved notification target '{name}' ({kind}).[/green]")


@app.command("list")
def list_targets(ctx: typer.Context) -> None:
    """List configured notification targets."""
    state = ctx.obj
    targets = load_targets()
    rows = [[t.name, t.kind, t.webhook_url] for t in sorted(targets.values(), key=lambda t: t.name)]
    if state.output.is_json:
        state.output.emit_json(
            [{"name": t.name, "kind": t.kind, "webhook_url": t.webhook_url, "extra": t.extra} for t in targets.values()]
        )
        return
    if not rows:
        state.output.print("No notification targets configured. Add one with `devtools notify add`.")
        return
    render_table(state.output, "Notification targets", ["name", "kind", "webhook_url"], rows)


@app.command("remove")
def remove(ctx: typer.Context, name: str = typer.Argument(...)) -> None:
    """Remove a configured notification target."""
    state = ctx.obj
    if not remove_target(name):
        fail(ctx, INVALID_USAGE, f"No notification target named '{name}'.")
    state.output.print(f"Removed notification target '{name}'.")


@app.command("send")
def send(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Notification target name."),
    message: str = typer.Argument(..., help="Message body to send."),
    event: str = typer.Option("devtools", "--event", help="Short event/title label."),
    field: List[str] = typer.Option([], "--field", help="Extra key=value fields (repeatable)."),
) -> None:
    """Send a one-off notification to a configured target."""
    state = ctx.obj
    if not state.settings.allow_network:
        fail(
            ctx,
            INVALID_USAGE,
            "`notify send` requires network access. Set allow_network = true in config.toml, "
            "then re-run `devtools notify send`.",
        )
    targets = load_targets()
    target = targets.get(name)
    if target is None:
        fail(ctx, INVALID_USAGE, f"No notification target named '{name}'. Run `devtools notify list`.")

    try:
        fields = _parse_fields(field)
    except NotifyError as exc:
        fail(ctx, INVALID_USAGE, str(exc))

    result = send_notification(target, event, message, fields=fields)

    if state.output.is_json:
        state.output.emit_json({"target": result.target, "ok": result.ok, "status_code": result.status_code, "error": result.error})
    elif result.ok:
        state.output.print(f"[green]Sent to '{name}' ({result.status_code}).[/green]")
    else:
        state.output.error(f"Failed to notify '{name}': {result.error or result.status_code}")

    if not result.ok:
        fail(ctx, GENERAL_ERROR, f"Notification to '{name}' failed.")


@app.command("test")
def test(ctx: typer.Context, name: str = typer.Argument(...)) -> None:
    """Send a canned test message to a configured target."""
    send(ctx, name=name, message="This is a test notification from devtools.", event="devtools test", field=[])
