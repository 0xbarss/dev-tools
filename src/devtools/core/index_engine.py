"""`devtools index` — persistent SQLite project index.

Proposal deep-dive #1 (P0, Large) plus backlog #50 (incremental indexing).
Every command currently re-walks the filesystem; this index turns
`stats`/`grep`/`deps`/`search` into near-instant lookups once built, and is
the on-disk store `search_engine.py`'s `--semantic` mode reads its vectors
from. Zero new hard dependencies — `sqlite3` is stdlib.

Cache-invalidation strategy (the proposal's own named drawback for this
feature): a file is only re-read/re-hashed/re-vectorized when its mtime has
changed since the last index build. `is_fresh()` does a cheap directory scan
(mtimes only, no file reads) to decide whether callers should trust the
index as-is or trigger a rebuild.
"""

from __future__ import annotations

import math
import re
import sqlite3
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from devtools.core.collector import collect_files
from devtools.core.filesystem import file_hash
from devtools.core.ignore_rules import IgnoreRules
from devtools.core.scanner import detect_language
from devtools.utils.paths import index_db_path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    path TEXT PRIMARY KEY,
    language TEXT NOT NULL,
    size INTEGER NOT NULL,
    mtime REAL NOT NULL,
    hash TEXT
);
CREATE TABLE IF NOT EXISTS vectors (
    path TEXT PRIMARY KEY REFERENCES files(path) ON DELETE CASCADE,
    terms TEXT NOT NULL  -- JSON: {"term": tf_weight, ...}
);
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""

_TOKEN_RE = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]{1,}")


@dataclass
class IndexStats:
    file_count: int
    has_vectors: bool
    built_at: str | None


@contextmanager
def _connect(project_name: str):
    path = index_db_path(project_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.executescript(_SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text)]


def build(
    root: Path,
    project_name: str,
    ignore_rules: IgnoreRules,
    with_vectors: bool = False,
    incremental: bool = True,
) -> int:
    """(Re)build the index for a project. Returns the number of files
    (re)written. With `incremental=True` (the default), a file whose mtime
    matches what's already stored is left untouched — only changed or new
    files are re-hashed/re-vectorized, per backlog #50."""
    import json as _json

    with _connect(project_name) as conn:
        existing = {row[0]: row[1] for row in conn.execute("SELECT path, mtime FROM files")}
        seen_paths: set[str] = set()
        changed = 0

        result = collect_files(root, ignore_rules) if with_vectors else None
        content_by_path = {f.rel_path: f.content for f in result.files} if result else {}

        doc_freq: Counter[str] = Counter()
        term_counts_by_path: dict[str, Counter[str]] = {}

        for entry_path in ignore_rules.filtered_walk():
            try:
                stat = entry_path.stat()
            except OSError:
                continue
            rel = entry_path.relative_to(root).as_posix()
            seen_paths.add(rel)
            mtime = stat.st_mtime

            if incremental and existing.get(rel) == mtime:
                if with_vectors and rel in content_by_path:
                    counts = Counter(_tokenize(content_by_path[rel]))
                    term_counts_by_path[rel] = counts
                    doc_freq.update(counts.keys())
                continue

            changed += 1
            digest = file_hash(entry_path)
            language = detect_language(entry_path)
            conn.execute(
                "INSERT INTO files (path, language, size, mtime, hash) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(path) DO UPDATE SET language=excluded.language, size=excluded.size, "
                "mtime=excluded.mtime, hash=excluded.hash",
                (rel, language, stat.st_size, mtime, digest),
            )
            if with_vectors and rel in content_by_path:
                counts = Counter(_tokenize(content_by_path[rel]))
                term_counts_by_path[rel] = counts
                doc_freq.update(counts.keys())

        stale = set(existing) - seen_paths
        if stale:
            conn.executemany("DELETE FROM files WHERE path = ?", [(p,) for p in stale])

        if with_vectors:
            num_docs = max(len(term_counts_by_path), 1)
            for rel, counts in term_counts_by_path.items():
                total = sum(counts.values()) or 1
                weights = {}
                for term, tf in counts.items():
                    idf = math.log((num_docs + 1) / (doc_freq.get(term, 0) + 1)) + 1.0
                    weights[term] = (tf / total) * idf
                conn.execute(
                    "INSERT INTO vectors (path, terms) VALUES (?, ?) "
                    "ON CONFLICT(path) DO UPDATE SET terms=excluded.terms",
                    (rel, _json.dumps(weights)),
                )
            for rel in stale:
                conn.execute("DELETE FROM vectors WHERE path = ?", (rel,))

        import time as _time

        conn.execute(
            "INSERT INTO meta (key, value) VALUES ('built_at', ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (str(_time.time()),),
        )
        return changed


def is_fresh(root: Path, project_name: str, ignore_rules: IgnoreRules) -> bool:
    """Cheap freshness check: compares current on-disk mtimes/paths against
    the index, without reading any file content."""
    path = index_db_path(project_name)
    if not path.is_file():
        return False
    with _connect(project_name) as conn:
        existing = {row[0]: row[1] for row in conn.execute("SELECT path, mtime FROM files")}
    seen: set[str] = set()
    for entry_path in ignore_rules.filtered_walk():
        try:
            mtime = entry_path.stat().st_mtime
        except OSError:
            continue
        rel = entry_path.relative_to(root).as_posix()
        seen.add(rel)
        if existing.get(rel) != mtime:
            return False
    return seen == set(existing)


def get_stats(project_name: str) -> IndexStats:
    with _connect(project_name) as conn:
        (file_count,) = conn.execute("SELECT COUNT(*) FROM files").fetchone()
        (vector_count,) = conn.execute("SELECT COUNT(*) FROM vectors").fetchone()
        row = conn.execute("SELECT value FROM meta WHERE key = 'built_at'").fetchone()
    return IndexStats(file_count=file_count, has_vectors=vector_count > 0, built_at=row[0] if row else None)


def load_vectors(project_name: str) -> dict[str, dict[str, float]]:
    import json as _json

    with _connect(project_name) as conn:
        rows = conn.execute("SELECT path, terms FROM vectors").fetchall()
    return {path: _json.loads(terms) for path, terms in rows}


def query_vector(query: str, corpus_vectors: dict[str, dict[str, float]]) -> dict[str, float]:
    """Build a query vector using plain term frequency, weighted by the
    average IDF-derived weight already present per term across the corpus
    (so common code tokens like 'self'/'return' don't dominate)."""
    terms = _tokenize(query)
    if not terms:
        return {}
    tf = Counter(terms)
    total = sum(tf.values())
    # crude idf proxy: how many docs each term appears in already, from vectors
    doc_hits: Counter[str] = Counter()
    for weights in corpus_vectors.values():
        for term in weights:
            doc_hits[term] += 1
    num_docs = max(len(corpus_vectors), 1)
    out = {}
    for term, count in tf.items():
        idf = math.log((num_docs + 1) / (doc_hits.get(term, 0) + 1)) + 1.0
        out[term] = (count / total) * idf
    return out


def cosine_similarity(a: dict[str, float], b: dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    common = set(a) & set(b)
    dot = sum(a[t] * b[t] for t in common)
    norm_a = math.sqrt(sum(v * v for v in a.values()))
    norm_b = math.sqrt(sum(v * v for v in b.values()))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def delete_index(project_name: str) -> bool:
    path = index_db_path(project_name)
    if path.is_file():
        path.unlink()
        return True
    return False