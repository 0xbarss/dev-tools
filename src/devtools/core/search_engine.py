"""Semantic-ish concept search — Phase 3 staged plan from spec §6 `search`.

Phase 3 (implemented here): keyword/synonym expansion + grep under the hood,
no embeddings, no network. `--build-index` is reserved for the later,
opt-in local-embedding stage and intentionally raises NotImplementedError
so it fails loudly rather than silently degrading to keyword search.
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
    score: int
    matched_terms: list[str]
    sample_matches: list[GrepMatch]


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


def build_index(root: Path) -> None:
    """Reserved for the later, opt-in local-embedding search stage (spec §6)."""
    raise NotImplementedError(
        "Semantic embedding search is not implemented yet (staged for a later, "
        "opt-in release per the spec's 'Later, opt-in' plan for `search`). "
        "Use keyword search (the default) for now."
    )