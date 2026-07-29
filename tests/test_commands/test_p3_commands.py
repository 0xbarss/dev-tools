from __future__ import annotations

import json

from typer.testing import CliRunner

from devtools.cli import app

runner = CliRunner()


def _register(root, name="demo"):
    result = runner.invoke(app, ["project", "add", name, str(root)])
    assert result.exit_code == 0, result.output
    return name


# --- notify ------------------------------------------------------------------


def test_notify_add_list_remove_roundtrip(tmp_path):
    result = runner.invoke(app, ["notify", "add", "eng-slack", "https://hooks.slack.com/services/x", "--kind", "slack"])
    assert result.exit_code == 0, result.output

    result = runner.invoke(app, ["--json", "notify", "list"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert any(t["name"] == "eng-slack" for t in payload)

    result = runner.invoke(app, ["notify", "remove", "eng-slack"])
    assert result.exit_code == 0

    result = runner.invoke(app, ["--json", "notify", "list"])
    payload = json.loads(result.output)
    assert not any(t["name"] == "eng-slack" for t in payload)


def test_notify_add_rejects_unknown_kind():
    result = runner.invoke(app, ["notify", "add", "x", "https://example.com", "--kind", "carrier-pigeon"])
    assert result.exit_code == 2


def test_notify_remove_unknown_target_fails():
    result = runner.invoke(app, ["notify", "remove", "does-not-exist"])
    assert result.exit_code == 2


def test_notify_send_requires_allow_network(tmp_path):
    runner.invoke(app, ["notify", "add", "t1", "https://example.com/hook", "--kind", "generic"])
    result = runner.invoke(app, ["notify", "send", "t1", "hello"])
    assert result.exit_code == 2
    assert "allow_network" in result.output


def test_notify_send_unknown_target_fails(tmp_path):
    result = runner.invoke(app, ["config", "set", "allow_network", "true"])
    assert result.exit_code == 0
    result = runner.invoke(app, ["notify", "send", "no-such-target", "hi"])
    assert result.exit_code == 2


# --- compliance ----------------------------------------------------------------


def test_compliance_report_renders_score(sample_repo):
    name = _register(sample_repo, "compliance_demo")
    result = runner.invoke(app, ["compliance", "report", name])
    assert result.exit_code == 0
    assert "score" in result.output.lower()


def test_compliance_report_json_output_shape(sample_repo):
    name = _register(sample_repo, "compliance_json")
    result = runner.invoke(app, ["--json", "compliance", "report", name])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert "score" in payload
    assert "findings" in payload
    assert 0 <= payload["score"] <= 100


def test_compliance_report_writes_html_file(sample_repo, tmp_path):
    name = _register(sample_repo, "compliance_html")
    out = tmp_path / "report.html"
    result = runner.invoke(app, ["compliance", "report", name, "--html", str(out)])
    assert result.exit_code == 0
    assert out.exists()
    assert "<html" in out.read_text()


def test_compliance_report_check_flag_exit_code(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[project]\nname="s"\ndependencies=["a>=1.0"]\n')
    name = _register(tmp_path, "compliance_ci")
    result = runner.invoke(app, ["compliance", "report", name, "--deny", "unknown", "--check"])
    assert result.exit_code == 5


def test_compliance_report_unknown_notify_target_fails(sample_repo):
    name = _register(sample_repo, "compliance_notify_missing")
    result = runner.invoke(app, ["compliance", "report", name, "--notify", "no-such-target"])
    assert result.exit_code == 2


# --- marketplace -----------------------------------------------------------


def test_marketplace_list_includes_curated_entries():
    result = runner.invoke(app, ["marketplace", "list"])
    assert result.exit_code == 0
    assert "secrets-scan" in result.output


def test_marketplace_add_and_list_json():
    result = runner.invoke(app, ["marketplace", "add", "my-check", "does a thing", "--category", "custom"])
    assert result.exit_code == 0

    result = runner.invoke(app, ["--json", "marketplace", "list"])
    payload = json.loads(result.output)
    assert any(e["name"] == "my-check" for e in payload)


def test_marketplace_remove_curated_entry_fails():
    result = runner.invoke(app, ["marketplace", "remove", "secrets-scan"])
    assert result.exit_code == 2


def test_marketplace_generate_writes_html(tmp_path):
    out = tmp_path / "site.html"
    result = runner.invoke(app, ["marketplace", "generate", "--output", str(out)])
    assert result.exit_code == 0
    assert out.exists()
    assert "<html" in out.read_text()


# --- investigate -------------------------------------------------------------


def test_investigate_fails_cleanly_without_ai_provider(sample_repo):
    name = _register(sample_repo, "investigate_demo")
    result = runner.invoke(app, ["investigate", name, "how does auth work"])
    assert result.exit_code == 1
    assert "No AI provider configured" in result.output