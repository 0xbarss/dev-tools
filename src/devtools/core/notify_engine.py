"""Enterprise notifications — Slack/Teams/Jira/generic webhooks (backlog §10,
Prioritized Backlog: "Enterprise notifications (Slack/Jira/Teams)", P2).

Targets are named webhook configurations stored locally
(`~/.config/devtools/notifications.json`), the same JSON-store pattern as
`alias_store.py`. Sending a notification is an outbound network call, so —
matching the project's `allow_network` philosophy used by `update.py` and
`llm_client.py` — callers must check `settings.allow_network` themselves
before invoking `send_notification`; this module never reads Settings
directly, to keep it independently unit-testable.

No provider SDKs required: every adapter is a plain HTTP POST built with the
stdlib `urllib`, so this adds zero new hard dependencies (same rationale as
`llm_client.py`).
"""

from __future__ import annotations

import json as _json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

try:
    import orjson
except ImportError:  # pragma: no cover
    orjson = None  # type: ignore[assignment]

from devtools.utils.paths import notify_targets_file_path

SUPPORTED_KINDS = ("slack", "teams", "jira", "generic")


class NotifyError(RuntimeError):
    """Raised for target configuration or send failures."""


@dataclass
class NotifyTarget:
    name: str
    kind: str  # one of SUPPORTED_KINDS
    webhook_url: str
    extra: dict = field(default_factory=dict)  # e.g. jira: {"project_key": "OPS"}

    def to_dict(self) -> dict:
        return {"kind": self.kind, "webhook_url": self.webhook_url, "extra": self.extra}

    @staticmethod
    def from_dict(name: str, data: dict) -> "NotifyTarget":
        return NotifyTarget(
            name=name,
            kind=data.get("kind", "generic"),
            webhook_url=data.get("webhook_url", ""),
            extra=data.get("extra", {}) or {},
        )


@dataclass
class NotifyResult:
    target: str
    ok: bool
    status_code: Optional[int] = None
    error: Optional[str] = None


def _dumps(obj) -> bytes:
    if orjson is not None:
        return orjson.dumps(obj, option=orjson.OPT_INDENT_2)
    return _json.dumps(obj, indent=2).encode("utf-8")


def _loads(data: bytes | str):
    if orjson is not None:
        return orjson.loads(data)
    return _json.loads(data)


def load_targets(path: Path | None = None) -> dict[str, NotifyTarget]:
    p = path or notify_targets_file_path()
    if not p.is_file():
        return {}
    raw = _loads(p.read_bytes())
    return {name: NotifyTarget.from_dict(name, data) for name, data in raw.items()}


def save_targets(targets: dict[str, NotifyTarget], path: Path | None = None) -> Path:
    p = path or notify_targets_file_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(_dumps({name: t.to_dict() for name, t in targets.items()}))
    return p


def add_target(
    name: str,
    kind: str,
    webhook_url: str,
    extra: dict | None = None,
    path: Path | None = None,
) -> dict[str, NotifyTarget]:
    kind = kind.strip().lower()
    if kind not in SUPPORTED_KINDS:
        raise NotifyError(f"Unknown notification kind {kind!r}. Supported: {', '.join(SUPPORTED_KINDS)}.")
    if not webhook_url.startswith(("http://", "https://")):
        raise NotifyError(f"webhook_url must be an http(s) URL, got {webhook_url!r}.")
    targets = load_targets(path)
    targets[name] = NotifyTarget(name=name, kind=kind, webhook_url=webhook_url, extra=extra or {})
    save_targets(targets, path)
    return targets


def remove_target(name: str, path: Path | None = None) -> bool:
    targets = load_targets(path)
    if name not in targets:
        return False
    del targets[name]
    save_targets(targets, path)
    return True


def build_payload(target: NotifyTarget, event: str, message: str, fields: dict | None = None) -> dict:
    """Shape the outgoing JSON body for the target's provider."""
    fields = fields or {}

    if target.kind == "slack":
        text = f"*{event}*\n{message}"
        if fields:
            text += "\n" + "\n".join(f"- *{k}*: {v}" for k, v in fields.items())
        return {"text": text}

    if target.kind == "teams":
        facts = [{"name": k, "value": str(v)} for k, v in fields.items()]
        return {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "summary": event,
            "title": event,
            "text": message,
            "sections": [{"facts": facts}] if facts else [],
        }

    if target.kind == "jira":
        # Generic "create issue" style payload for a Jira Automation/incoming
        # webhook. Real Jira Cloud REST auth (email + API token) is layered
        # on separately via `extra`, since this module never handles secrets
        # itself; the webhook endpoint is expected to carry its own auth.
        payload = {
            "fields": {
                "summary": f"[{event}] {message}"[:255],
                "description": message,
                **({"project": {"key": target.extra["project_key"]}} if "project_key" in target.extra else {}),
                **({"issuetype": {"name": target.extra["issue_type"]}} if "issue_type" in target.extra else {}),
            }
        }
        if fields:
            payload["fields"]["labels"] = [f"{k}:{v}" for k, v in fields.items()]
        return payload

    # generic: raw event/message/fields envelope, caller's endpoint decides shape
    return {"event": event, "message": message, "fields": fields}


def send_notification(
    target: NotifyTarget,
    event: str,
    message: str,
    fields: dict | None = None,
    timeout: int = 10,
) -> NotifyResult:
    body = build_payload(target, event, message, fields)
    data = _json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        target.webhook_url, data=data, headers={"content-type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return NotifyResult(target=target.name, ok=200 <= resp.status < 300, status_code=resp.status)
    except urllib.error.HTTPError as exc:
        return NotifyResult(target=target.name, ok=False, status_code=exc.code, error=str(exc))
    except urllib.error.URLError as exc:
        return NotifyResult(target=target.name, ok=False, error=str(exc.reason))
