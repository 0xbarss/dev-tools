from __future__ import annotations

import pytest

from devtools.core.explain_engine import build_context, explain
from devtools.core.ignore_rules import IgnoreRules


class FakeClient:
    provider = "fake"

    def __init__(self):
        self.last_prompt = None
        self.last_system = None

    def complete(self, prompt, system=None):
        self.last_prompt = prompt
        self.last_system = system
        return "a helpful explanation"


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    (root / "auth.py").write_text("def authenticate(user):\n    return True\n")
    rules = IgnoreRules.build(root, base_ignored_dirs=["node_modules", "__pycache__"])
    return root, rules


def test_build_context_resolves_direct_file(project):
    root, rules = project
    ctx = build_context(root, rules, "auth.py")
    assert ctx.resolved_kind == "file"
    assert ctx.file_paths == ["auth.py"]
    assert "authenticate" in ctx.source_text


def test_build_context_resolves_symbol_via_search(project):
    root, rules = project
    ctx = build_context(root, rules, "authentication")
    assert ctx.resolved_kind == "symbol"
    assert "auth.py" in ctx.file_paths


def test_build_context_raises_for_unknown_target(project):
    root, rules = project
    with pytest.raises(ValueError):
        build_context(root, rules, "totally-unrelated-nonexistent-thing-xyz")


def test_explain_calls_client_with_context(project):
    root, rules = project
    client = FakeClient()
    result = explain(root, rules, "auth.py", client)
    assert result == "a helpful explanation"
    assert "authenticate" in client.last_prompt
    assert client.last_system is not None