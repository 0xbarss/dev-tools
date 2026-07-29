"""Semantic-ish concept search — Phase 3 staged plan from spec §6 `search`,
plus true semantic search (proposal deep-dive #2).

Phase 3 (keyword mode, default): keyword/synonym expansion + grep under the
hood, no embeddings, no network.

Semantic mode (`--semantic`, proposal deep-dive #2): ranks files by cosine
similarity between a lightweight, dependency-free TF-IDF vector of the query
and each file's vector, both computed/stored via `core/index_engine.py`.
This is intentionally *not* a neural embedding model — it needs zero new
dependencies and zero network access, matching the project's existing
`allow_network` philosophy — but it answers the same "rank by meaning, not
just keyword overlap" need the spec's original placeholder was reserved for.
A real embedding backend (sentence-transformers/onnxruntime, or Ollama) can
be added later as an alternate vector source without changing this module's
public shape. `build_index()` populates the vectors; `search(..., semantic=True)`
without a built index falls back to keyword search with a warning rather
than erroring.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from devtools.core.grep_engine import GrepMatch, grep
from devtools.core.ignore_rules import IgnoreRules

_STOPWORDS = {
    "a", "an", "the", "is", "are", "do", "does", "did", "how", "what", "where",
    "when", "why", "who", "which", "to", "of", "in", "on", "for", "with", "and",
    "or", "work", "works", "working", "about", "this", "that", "it", "does",
}

# Small, hand-curated concept -> synonym map covering the examples named in
# the spec (`authentication`, `database`, `payment`, `cache`, `jwt`, `endpoint`, ...).
CONCEPT_SYNONYMS: dict[str, list[str]] = {
    "authentication": ["auth", "login", "signin", "sign_in", "authenticate", "session", "credential"],
    "authorization": ["authz", "permission", "acl", "role", "rbac", "scope"],
    "database": ["db", "sql", "query", "orm", "repository", "model", "migration"],
    "payment": ["billing", "charge", "invoice", "stripe", "checkout", "subscription", "price"],
    "cache": ["caching", "memoize", "redis", "ttl", "lru"],
    "jwt": ["token", "bearer", "claims", "jsonwebtoken"],
    "endpoint": ["route", "handler", "controller", "api", "view", "resource"],
    "logging": ["log", "logger", "telemetry", "trace"],
    "config": ["configuration", "settings", "env", "environment"],
    "test": ["tests", "spec", "fixture", "mock", "assert"],
    "error": ["exception", "err", "failure", "traceback"],
    "queue": ["worker", "job", "task", "celery", "background"],
}


def tokenize_query(text: str) -> list[str]:
    """Split free text into significant words, dropping stopwords/short tokens."""
    words = re.findall(r"[a-zA-Z0-9_]+", text.lower())
    return [w for w in words if w not in _STOPWORDS and len(w) > 2]


def _expand_single(key: str) -> list[str]:
    terms = [key]
    for base, synonyms in CONCEPT_SYNONYMS.items():
        if key == base:
            terms.extend(synonyms)
        elif key in synonyms:
            terms.append(base)
            terms.extend(s for s in synonyms if s != key)
    return terms


def expand_query(concept: str) -> list[str]:
    """Return [concept, *synonyms] for a single concept word, or, for
    free-text/multi-word input (e.g. a natural-language question passed to
    `context`), the union of expansions for each significant word.
    """
    words = tokenize_query(concept)
    if words:
        terms: list[str] = []
        for w in words:
            terms.extend(_expand_single(w))
    else:
        terms = _expand_single(concept.strip().lower())

    # de-dupe, preserve order
    seen = set()
    out = []
    for t in terms:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


@dataclass
class SearchHit:
    rel_path: str
    score: float
    matched_terms: list[str]
    sample_matches: list[GrepMatch]


def semantic_search(
    root: Path,
    project_name: str,
    concept: str,
    max_samples_per_file: int = 3,
    ignore_rules: IgnoreRules | None = None,
):
    """Rank files by cosine similarity against the project's TF-IDF index.

    Returns (hits, used_semantic). `used_semantic` is False when no index
    with vectors exists yet -- callers should fall back to keyword search
    and warn the user to run `devtools search --build-index` first.
    """
    from devtools.core import index_engine

    corpus_vectors = index_engine.load_vectors(project_name)
    if not corpus_vectors:
        return [], False

    expanded_query = " ".join(expand_query(concept)) or concept
    query_vec = index_engine.query_vector(expanded_query, corpus_vectors)
    if not query_vec:
        return [], True

    scored = [
        (rel_path, index_engine.cosine_similarity(query_vec, vec))
        for rel_path, vec in corpus_vectors.items()
    ]
    scored = [(p, s) for p, s in scored if s > 0]
    scored.sort(key=lambda pair: pair[1], reverse=True)

    hits = []
    matched_terms = sorted(query_vec, key=lambda t: query_vec[t], reverse=True)[:8]
    for rel_path, score in scored:
        sample_matches: list[GrepMatch] = []
        if ignore_rules is not None:
            for term in matched_terms:
                if len(sample_matches) >= max_samples_per_file:
                    break
                for m in grep(root, ignore_rules, term, regex=False, languages=None, case_sensitive=False):
                    if m.rel_path == rel_path:
                        sample_matches.append(m)
                        if len(sample_matches) >= max_samples_per_file:
                            break
        hits.append(
            SearchHit(rel_path=rel_path, score=round(score, 4), matched_terms=matched_terms, sample_matches=sample_matches)
        )
    return hits, True


def search(
    root: Path,
    ignore_rules: IgnoreRules,
    concept: str,
    languages: list[str] | None = None,
    max_samples_per_file: int = 3,
) -> list[SearchHit]:
    terms = expand_query(concept)
    per_file_matches: dict[str, list[GrepMatch]] = defaultdict(list)
    per_file_terms: dict[str, set] = defaultdict(set)

    for term in terms:
        for m in grep(root, ignore_rules, term, regex=False, languages=languages, case_sensitive=False):
            per_file_matches[m.rel_path].append(m)
            per_file_terms[m.rel_path].add(term)

    hits = []
    for rel_path, matches in per_file_matches.items():
        # score rewards both match volume and breadth of distinct concept terms found
        score = len(matches) + 3 * len(per_file_terms[rel_path])
        hits.append(
            SearchHit(
                rel_path=rel_path,
                score=score,
                matched_terms=sorted(per_file_terms[rel_path]),
                sample_matches=matches[:max_samples_per_file],
            )
        )
    hits.sort(key=lambda h: h.score, reverse=True)
    return hits


def build_index(root: Path, project_name: str, ignore_rules: IgnoreRules) -> int:
    """Build (or refresh) the local TF-IDF vector index used by `--semantic`.

    No network, no model download -- see the module docstring for why this
    isn't a neural embedding model. Returns the number of files (re)indexed.
    """
    from devtools.core import index_engine

    return index_engine.build(root, project_name, ignore_rules, with_vectors=True)