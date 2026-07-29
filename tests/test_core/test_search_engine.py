from __future__ import annotations

from devtools.core.ignore_rules import IgnoreRules
from devtools.core.search_engine import build_index, expand_query, search, semantic_search, tokenize_query


def test_expand_query_includes_synonyms():
    terms = expand_query("authentication")
    assert "auth" in terms
    assert "login" in terms


def test_expand_query_reverse_lookup_from_synonym():
    terms = expand_query("auth")
    assert "authentication" in terms


def test_tokenize_query_drops_stopwords():
    words = tokenize_query("how does auth work")
    assert words == ["auth"]


def test_expand_query_handles_multiword_free_text():
    terms = expand_query("how does auth work")
    assert "auth" in terms
    assert "authenticate" in terms


def test_search_ranks_relevant_file_first(sample_repo):
    rules = IgnoreRules.build(sample_repo, base_ignored_dirs=["node_modules", "__pycache__"])
    hits = search(sample_repo, rules, "authentication")
    assert hits, "expected at least one hit"
    assert hits[0].rel_path == "src/auth.py"


def test_search_no_hits_for_absent_concept(sample_repo):
    rules = IgnoreRules.build(sample_repo, base_ignored_dirs=["node_modules", "__pycache__"])
    hits = search(sample_repo, rules, "kubernetes")
    assert hits == []


def test_build_index_and_semantic_search(sample_repo, monkeypatch):
    monkeypatch.setenv("DEVTOOLS_CACHE_DIR", str(sample_repo.parent / "_cache"))
    rules = IgnoreRules.build(sample_repo, base_ignored_dirs=["node_modules", "__pycache__"])
    count = build_index(sample_repo, "sem_test_project", rules)
    assert count > 0

    hits, used_semantic = semantic_search(sample_repo, "sem_test_project", "authentication", ignore_rules=rules)
    assert used_semantic is True
    assert hits, "expected at least one semantic hit"
    assert hits[0].rel_path == "src/auth.py"


def test_semantic_search_falls_back_without_index(tmp_path, monkeypatch):
    monkeypatch.setenv("DEVTOOLS_CACHE_DIR", str(tmp_path / "_cache_empty"))
    hits, used_semantic = semantic_search(tmp_path, "nonexistent_project_xyz", "authentication")
    assert used_semantic is False
    assert hits == []