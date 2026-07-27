from __future__ import annotations

import pytest

from devtools.core.ignore_rules import IgnoreRules
from devtools.core.search_engine import build_index, expand_query, search, tokenize_query


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


def test_build_index_not_implemented(tmp_path):
    with pytest.raises(NotImplementedError):
        build_index(tmp_path)