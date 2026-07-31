from __future__ import annotations

import time

import pytest

from devtools.core import rag_index
from devtools.core.ignore_rules import IgnoreRules


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setenv("DEVTOOLS_INDEX_DIR", str(tmp_path / "_index"))
    root = tmp_path / "proj"
    root.mkdir()
    (root / "auth.py").write_text(
        "def login(user, password):\n"
        "    return authenticate(user, password)\n\n"
        "def authenticate(user, password):\n"
        "    return True\n"
    )
    (root / "payments.py").write_text(
        "def charge_card(amount, token):\n"
        "    invoice = create_invoice(amount)\n"
        "    return invoice\n\n"
        "def create_invoice(amount):\n"
        "    return {'amount': amount}\n"
    )
    rules = IgnoreRules.build(root, base_ignored_dirs=["node_modules", "__pycache__"])
    return root, rules


def test_split_into_chunks_never_spans_files_and_covers_all_lines():
    content = "\n".join(f"line {i}" for i in range(1, 21))
    chunks = rag_index.split_into_chunks(content, chunk_tokens=5)
    assert chunks  # produced at least one chunk
    # every line covered exactly once, in order
    covered = []
    for c in chunks:
        covered.extend(range(c.start_line, c.end_line + 1))
    assert covered == list(range(1, 21))


def test_build_indexes_all_files_into_chunks(project):
    root, rules = project
    stats = rag_index.build(root, "rag_demo", rules)
    assert stats.files_indexed == 2
    assert stats.files_changed == 2
    assert stats.chunks_indexed >= 2

    index_stats = rag_index.get_stats("rag_demo")
    assert index_stats.file_count == 2
    assert index_stats.chunk_count == stats.chunks_indexed
    assert index_stats.built_at is not None


def test_is_fresh_reflects_mtime_changes(project):
    root, rules = project
    rag_index.build(root, "rag_fresh", rules)
    assert rag_index.is_fresh(root, "rag_fresh", rules) is True

    time.sleep(0.01)
    (root / "auth.py").write_text((root / "auth.py").read_text() + "\n# changed\n")
    assert rag_index.is_fresh(root, "rag_fresh", rules) is False


def test_incremental_rebuild_only_touches_changed_files(project):
    root, rules = project
    rag_index.build(root, "rag_incr", rules)

    time.sleep(0.01)
    (root / "payments.py").write_text((root / "payments.py").read_text() + "\n# bump\n")
    stats = rag_index.build(root, "rag_incr", rules)
    assert stats.files_changed == 1
    assert stats.files_indexed == 2


def test_retrieve_ranks_relevant_chunk_first(project):
    root, rules = project
    rag_index.build(root, "rag_search", rules)

    # Plain TF-IDF over literal tokens (no synonym expansion, unlike
    # search_engine's keyword mode) -- query with terms that actually
    # appear in auth.py.
    hits = rag_index.retrieve("rag_search", "login authenticate password", top_k=5)
    assert hits
    assert hits[0].rel_path == "auth.py"


def test_retrieve_returns_empty_without_a_built_index(tmp_path, monkeypatch):
    monkeypatch.setenv("DEVTOOLS_INDEX_DIR", str(tmp_path / "_index_empty"))
    assert rag_index.retrieve("never_built_project", "anything") == []


def test_ask_reports_missing_index_without_calling_the_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DEVTOOLS_INDEX_DIR", str(tmp_path / "_index_empty2"))

    class ExplodingClient:
        provider = "fake"

        def complete(self, prompt, system=None):
            raise AssertionError("should not be called when no index exists")

    result = rag_index.ask("never_built_project2", "anything", ExplodingClient())
    assert result.used_index is False
    assert "devtools index build --rag" in result.answer


def test_ask_grounds_answer_in_retrieved_chunks(project):
    root, rules = project
    rag_index.build(root, "rag_ask", rules)

    class FakeClient:
        provider = "fake"

        def __init__(self):
            self.last_prompt = None

        def complete(self, prompt, system=None):
            self.last_prompt = prompt
            return "Authentication happens in auth.py via login/authenticate."

    client = FakeClient()
    result = rag_index.ask("rag_ask", "login authenticate password", client, top_k=3)
    assert result.used_index is True
    assert result.sources
    assert result.sources[0].rel_path == "auth.py"
    assert "auth.py" in client.last_prompt


def test_delete_index_removes_the_database_file(project):
    root, rules = project
    rag_index.build(root, "rag_delete", rules)
    assert rag_index.delete_index("rag_delete") is True
    assert rag_index.delete_index("rag_delete") is False
    assert rag_index.get_stats("rag_delete").chunk_count == 0
