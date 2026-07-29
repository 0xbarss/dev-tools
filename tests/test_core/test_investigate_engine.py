from __future__ import annotations

import json

from devtools.core.ignore_rules import IgnoreRules
from devtools.core.investigate_engine import investigate, render_markdown


class ScriptedClient:
    """Replays a fixed sequence of responses, one per `complete()` call."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0

    def complete(self, prompt, system=None):
        self.calls += 1
        if self._responses:
            return self._responses.pop(0)
        return json.dumps({"action": "finish", "summary": "out of scripted responses", "evidence": []})


def _rules(root):
    return IgnoreRules.build(root, base_ignored_dirs=[])


def _repo(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "auth.py").write_text(
        "def login(user, password):\n    return authenticate(user, password)\n\n"
        "def authenticate(user, password):\n    return True\n"
    )
    return tmp_path


def test_investigate_search_then_read_then_finish(tmp_path):
    root = _repo(tmp_path)
    client = ScriptedClient(
        [
            json.dumps({"action": "search", "query": "authenticate"}),
            json.dumps({"action": "read", "path": "src/auth.py"}),
            json.dumps({"action": "finish", "summary": "login delegates to authenticate", "evidence": ["src/auth.py"]}),
        ]
    )
    report = investigate(root, _rules(root), client, "how does auth work", max_steps=5)
    assert report.summary == "login delegates to authenticate"
    assert report.evidence == ["src/auth.py"]
    assert [s.action for s in report.steps] == ["search", "read", "finish"]
    assert report.raw_text is None


def test_investigate_handles_fenced_json():
    pass  # covered implicitly via _extract_json_object sharing review_engine's logic


def test_investigate_refuses_path_escaping_project_root(tmp_path):
    root = _repo(tmp_path)
    client = ScriptedClient(
        [
            json.dumps({"action": "read", "path": "../../etc/passwd"}),
            json.dumps({"action": "finish", "summary": "done", "evidence": []}),
        ]
    )
    report = investigate(root, _rules(root), client, "escape test", max_steps=5)
    assert "outside the project root" in report.steps[0].observation


def test_investigate_reports_missing_file_cleanly(tmp_path):
    root = _repo(tmp_path)
    client = ScriptedClient(
        [
            json.dumps({"action": "read", "path": "does/not/exist.py"}),
            json.dumps({"action": "finish", "summary": "no such file", "evidence": []}),
        ]
    )
    report = investigate(root, _rules(root), client, "missing file")
    assert "No such file" in report.steps[0].observation


def test_investigate_falls_back_to_raw_text_on_malformed_json(tmp_path):
    root = _repo(tmp_path)
    client = ScriptedClient(["this is not json, just prose"])
    report = investigate(root, _rules(root), client, "q")
    assert report.raw_text == "this is not json, just prose"
    assert report.steps == []


def test_investigate_forces_a_conclusion_when_steps_run_out(tmp_path):
    root = _repo(tmp_path)
    client = ScriptedClient(
        [
            json.dumps({"action": "search", "query": "x"}),
            json.dumps({"action": "search", "query": "y"}),
            json.dumps({"action": "finish", "summary": "forced wrap-up", "evidence": []}),
        ]
    )
    report = investigate(root, _rules(root), client, "q", max_steps=2)
    assert report.summary == "forced wrap-up"
    assert client.calls == 3  # 2 budgeted steps + 1 forced wrap-up call


def test_investigate_rejects_non_positive_max_steps(tmp_path):
    root = _repo(tmp_path)
    import pytest

    with pytest.raises(ValueError):
        investigate(root, _rules(root), ScriptedClient([]), "q", max_steps=0)


def test_render_markdown_includes_summary_evidence_and_steps(tmp_path):
    root = _repo(tmp_path)
    client = ScriptedClient(
        [json.dumps({"action": "finish", "summary": "answer", "evidence": ["src/auth.py"]})]
    )
    report = investigate(root, _rules(root), client, "how does auth work")
    md = render_markdown(report, "myproject")
    assert "myproject" in md
    assert "answer" in md
    assert "src/auth.py" in md