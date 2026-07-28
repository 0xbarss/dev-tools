from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from devtools.core.notify_engine import (
    NotifyError,
    NotifyTarget,
    add_target,
    build_payload,
    load_targets,
    remove_target,
    save_targets,
    send_notification,
)


@pytest.fixture
def targets_path(tmp_path):
    return tmp_path / "notifications.json"


def test_add_and_load_target(targets_path):
    add_target("eng-slack", "slack", "https://hooks.slack.com/services/x", path=targets_path)
    targets = load_targets(targets_path)
    assert "eng-slack" in targets
    assert targets["eng-slack"].kind == "slack"
    assert targets["eng-slack"].webhook_url == "https://hooks.slack.com/services/x"


def test_add_target_rejects_unknown_kind(targets_path):
    with pytest.raises(NotifyError):
        add_target("x", "carrier-pigeon", "https://example.com", path=targets_path)


def test_add_target_rejects_non_http_url(targets_path):
    with pytest.raises(NotifyError):
        add_target("x", "slack", "not-a-url", path=targets_path)


def test_remove_target(targets_path):
    add_target("t1", "generic", "https://example.com/hook", path=targets_path)
    assert remove_target("t1", path=targets_path) is True
    assert load_targets(targets_path) == {}


def test_remove_missing_target_returns_false(targets_path):
    assert remove_target("does-not-exist", path=targets_path) is False


def test_load_targets_missing_file_returns_empty(targets_path):
    assert load_targets(targets_path) == {}


def test_targets_roundtrip_via_json(targets_path):
    add_target("j", "jira", "https://example.com/hook", extra={"project_key": "OPS"}, path=targets_path)
    save_targets(load_targets(targets_path), targets_path)  # roundtrip
    targets = load_targets(targets_path)
    assert targets["j"].extra == {"project_key": "OPS"}


# --- payload shaping ---------------------------------------------------------


def test_build_payload_slack_includes_event_and_fields():
    target = NotifyTarget(name="s", kind="slack", webhook_url="https://example.com")
    payload = build_payload(target, "devtools compliance report", "score 90/100", fields={"project": "backend"})
    assert "devtools compliance report" in payload["text"]
    assert "score 90/100" in payload["text"]
    assert "backend" in payload["text"]


def test_build_payload_teams_has_message_card_shape():
    target = NotifyTarget(name="t", kind="teams", webhook_url="https://example.com")
    payload = build_payload(target, "event", "message", fields={"score": 90})
    assert payload["@type"] == "MessageCard"
    assert payload["sections"][0]["facts"][0] == {"name": "score", "value": "90"}


def test_build_payload_jira_uses_project_key_and_issue_type():
    target = NotifyTarget(
        name="j", kind="jira", webhook_url="https://example.com", extra={"project_key": "OPS", "issue_type": "Task"}
    )
    payload = build_payload(target, "incident", "server down")
    assert payload["fields"]["project"] == {"key": "OPS"}
    assert payload["fields"]["issuetype"] == {"name": "Task"}
    assert "server down" in payload["fields"]["description"]


def test_build_payload_generic_is_a_plain_envelope():
    target = NotifyTarget(name="g", kind="generic", webhook_url="https://example.com")
    payload = build_payload(target, "ev", "msg", fields={"a": 1})
    assert payload == {"event": "ev", "message": "msg", "fields": {"a": 1}}


# --- sending (against a local mock server) -----------------------------------


@pytest.fixture
def mock_webhook_server():
    received = {}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers["Content-Length"])
            received["body"] = json.loads(self.rfile.read(length))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, *a):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_port, received
    finally:
        server.shutdown()


def test_send_notification_success(mock_webhook_server):
    port, received = mock_webhook_server
    target = NotifyTarget(name="t", kind="generic", webhook_url=f"http://127.0.0.1:{port}/hook")
    result = send_notification(target, "event", "message")
    assert result.ok is True
    assert result.status_code == 200
    assert received["body"] == {"event": "event", "message": "message", "fields": {}}


def test_send_notification_unreachable_host_fails_gracefully():
    target = NotifyTarget(name="t", kind="generic", webhook_url="http://127.0.0.1:1/hook")
    result = send_notification(target, "event", "message", timeout=2)
    assert result.ok is False
    assert result.error is not None
