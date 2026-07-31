"""`devtools ask` — persistent, chunk-level retrieval index over `collect`
output, for repeat AI Q&A without re-scanning/re-chunking/re-embedding the
project on every question (proposal deep-dive #25, previously 🟡 partial).

The annotated proposal's own note on this item: `core/index_engine.py`
already persists whole-file TF-IDF vectors (for `search --semantic`), and
`core/summarize_engine.py` already has a shared map-reduce chunk-and-summarize
primitive — but neither persists *chunked* `collect` output with per-chunk
vectors for cheap, repeated retrieval-augmented Q&A. This module is that
missing piece:

  1. `build(...)` collects the project (respecting a `--lang` filter), splits
     each file into fixed-size token chunks (a chunk never spans two files,
     so a citation always maps back to one real file + line range), computes
     a TF-IDF vector per chunk (same math as `index_engine`, just at chunk
     instead of whole-file granularity), and persists chunk text + vectors in
     a project-scoped SQLite database (kept separate from `index_engine`'s
     whole-file index — see `utils.paths.rag_index_db_path`).
  2. `retrieve(...)` embeds the question the same way and ranks stored chunks
     by cosine similarity — no filesystem access, no re-embedding, as long as
     the index is fresh.
  3. `ask(...)` feeds the top-k retrieved chunks to the configured
     `llm_client` to produce a grounded answer with cited sources.
  4. `is_fresh` / `get_stats` / `delete_index` mirror `index_engine`'s
     management surface for consistency.

No new hard dependency: this is TF-IDF over `sqlite3` (stdlib), matching the
project's "no required network" philosophy — same tradeoff `index_engine`'s
own docstring already makes explicit for `search --semantic`.
"""

from __future__ import annotations

import json as _json
import math
import re
import sqlite3
import time as _time
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from devtools.core.collector import collect_files
from devtools.core.ignore_rules import IgnoreRules
from devtools.core.llm_client import LLMClient
from devtools.utils.paths import rag_index_db_path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    path TEXT PRIMARY KEY,
    mtime REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL REFERENCES files(path) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    start_line INTEGER NOT NULL,
    end_line INTEGER NOT NULL,
    content TEXT NOT NULL,
    terms TEXT NOT NULL,
    UNIQUE(path, chunk_index)
);
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""

_TOKEN_RE = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]{1,}")

# Default chunk size in tokens. Kept small relative to summarize_engine's
# map-reduce chunk size (12k) since RAG chunks are meant to be individually
# retrieved and read, not just packed into one big map-pass prompt.
_DEFAULT_CHUNK_TOKENS = 400

_SYSTEM_PROMPT = (
    "You are answering a question about a codebase using only the numbered "
    "excerpts below, retrieved from a persistent chunk index. Answer the "
    "question directly and concisely. Cite the specific `path` (and line "
    "range, if relevant) for any claim you make. If the excerpts don't "
    "contain enough information to answer confidently, say so plainly "
    "rather than guessing."
)


@dataclass
class RagChunk:
    rel_path: str
    chunk_index: int
    start_line: int
    end_line: int
    content: str


@dataclass
class RetrievedChunk(RagChunk):
    score: float = 0.0


@dataclass
class RagBuildStats:
    files_indexed: int
    files_changed: int
    chunks_indexed: int


@dataclass
class RagIndexStats:
    file_count: int
    chunk_count: int
    built_at: str | None


@dataclass
class RagAnswer:
    answer: str
    sources: list[RetrievedChunk] = field(default_factory=list)
    used_index: bool = True


@contextmanager
def _connect(project_name: str):
    path = rag_index_db_path(project_name)
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


def split_into_chunks(content: str, chunk_tokens: int = _DEFAULT_CHUNK_TOKENS) -> list[RagChunk]:
    """Split one file's content into line-bounded chunks, greedily filling
    each chunk up to ~`chunk_tokens` (measured with the same tokenizer used
    everywhere else -- a rough word/identifier count, not tiktoken, so this
    stays dependency-free and fast for large repos)."""
    lines = content.splitlines()
    if not lines:
        return []

    chunks: list[RagChunk] = []
    current_lines: list[str] = []
    current_tokens = 0
    start_line = 1

    def _flush(end_line: int) -> None:
        nonlocal current_lines, current_tokens, start_line
        if current_lines:
            chunks.append(
                RagChunk(
                    rel_path="",  # filled in by caller
                    chunk_index=len(chunks),
                    start_line=start_line,
                    end_line=end_line,
                    content="\n".join(current_lines),
                )
            )
        current_lines = []
        current_tokens = 0
        start_line = end_line + 1

    for i, line in enumerate(lines, start=1):
        line_tokens = len(_tokenize(line)) or 1
        if current_lines and current_tokens + line_tokens > chunk_tokens:
            _flush(i - 1)
        current_lines.append(line)
        current_tokens += line_tokens
    _flush(len(lines))
    return chunks


def build(
    root: Path,
    project_name: str,
    ignore_rules: IgnoreRules,
    languages: list[str] | None = None,
    chunk_tokens: int = _DEFAULT_CHUNK_TOKENS,
    incremental: bool = True,
) -> RagBuildStats:
    """(Re)build the persistent chunk index for a project. With
    `incremental=True` (the default), a file whose mtime matches what's
    already stored is left untouched -- only changed/new files are
    re-chunked and re-vectorized, mirroring `index_engine.build`'s strategy."""
    result = collect_files(root, ignore_rules, languages=languages)

    with _connect(project_name) as conn:
        existing_mtimes = {row[0]: row[1] for row in conn.execute("SELECT path, mtime FROM files")}
        seen_paths: set[str] = set()
        files_changed = 0

        doc_freq: Counter[str] = Counter()
        chunk_terms_by_key: dict[tuple[str, int], Counter[str]] = {}
        changed_paths: set[str] = set()

        for f in result.files:
            path_obj = root / f.rel_path
            try:
                mtime = path_obj.stat().st_mtime
            except OSError:
                continue
            seen_paths.add(f.rel_path)

            unchanged = incremental and existing_mtimes.get(f.rel_path) == mtime
            if unchanged:
                # Still fold its existing chunk terms into doc_freq so the
                # corpus-wide IDF stays accurate, without touching its rows.
                for row in conn.execute(
                    "SELECT chunk_index, terms FROM chunks WHERE path = ?", (f.rel_path,)
                ):
                    terms = _json.loads(row[1])
                    doc_freq.update(terms.keys())
                continue

            files_changed += 1
            changed_paths.add(f.rel_path)
            conn.execute(
                "INSERT INTO files (path, mtime) VALUES (?, ?) "
                "ON CONFLICT(path) DO UPDATE SET mtime=excluded.mtime",
                (f.rel_path, mtime),
            )
            conn.execute("DELETE FROM chunks WHERE path = ?", (f.rel_path,))

            for chunk in split_into_chunks(f.content, chunk_tokens):
                counts = Counter(_tokenize(chunk.content))
                chunk_terms_by_key[(f.rel_path, chunk.chunk_index)] = counts
                doc_freq.update(counts.keys())
                conn.execute(
                    "INSERT INTO chunks (path, chunk_index, start_line, end_line, content, terms) "
                    "VALUES (?, ?, ?, ?, ?, '{}')",
                    (f.rel_path, chunk.chunk_index, chunk.start_line, chunk.end_line, chunk.content),
                )

        stale = set(existing_mtimes) - seen_paths
        if stale:
            conn.executemany("DELETE FROM files WHERE path = ?", [(p,) for p in stale])

        num_chunks = max(len(chunk_terms_by_key), 1)
        for (path, chunk_index), counts in chunk_terms_by_key.items():
            total = sum(counts.values()) or 1
            weights = {}
            for term, tf in counts.items():
                idf = math.log((num_chunks + 1) / (doc_freq.get(term, 0) + 1)) + 1.0
                weights[term] = (tf / total) * idf
            conn.execute(
                "UPDATE chunks SET terms = ? WHERE path = ? AND chunk_index = ?",
                (_json.dumps(weights), path, chunk_index),
            )

        (chunk_count,) = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()
        (file_count,) = conn.execute("SELECT COUNT(*) FROM files").fetchone()
        conn.execute(
            "INSERT INTO meta (key, value) VALUES ('built_at', ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (str(_time.time()),),
        )
        return RagBuildStats(files_indexed=file_count, files_changed=files_changed, chunks_indexed=chunk_count)


def is_fresh(root: Path, project_name: str, ignore_rules: IgnoreRules) -> bool:
    """Cheap freshness check: compares current on-disk mtimes for every
    currently-indexed file, without reading content or rebuilding vectors."""
    path = rag_index_db_path(project_name)
    if not path.is_file():
        return False
    with _connect(project_name) as conn:
        existing = {row[0]: row[1] for row in conn.execute("SELECT path, mtime FROM files")}
    if not existing:
        return False
    for rel_path, mtime in existing.items():
        try:
            if (root / rel_path).stat().st_mtime != mtime:
                return False
        except OSError:
            return False
    return True


def get_stats(project_name: str) -> RagIndexStats:
    with _connect(project_name) as conn:
        (file_count,) = conn.execute("SELECT COUNT(*) FROM files").fetchone()
        (chunk_count,) = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()
        row = conn.execute("SELECT value FROM meta WHERE key = 'built_at'").fetchone()
    return RagIndexStats(file_count=file_count, chunk_count=chunk_count, built_at=row[0] if row else None)


def delete_index(project_name: str) -> bool:
    path = rag_index_db_path(project_name)
    if path.is_file():
        path.unlink()
        return True
    return False


def _query_vector(query: str, doc_freq: Counter, num_chunks: int) -> dict[str, float]:
    terms = _tokenize(query)
    if not terms:
        return {}
    tf = Counter(terms)
    total = sum(tf.values())
    out = {}
    for term, count in tf.items():
        idf = math.log((num_chunks + 1) / (doc_freq.get(term, 0) + 1)) + 1.0
        out[term] = (count / total) * idf
    return out


def _cosine_similarity(a: dict[str, float], b: dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    common = set(a) & set(b)
    dot = sum(a[t] * b[t] for t in common)
    norm_a = math.sqrt(sum(v * v for v in a.values()))
    norm_b = math.sqrt(sum(v * v for v in b.values()))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def retrieve(project_name: str, question: str, top_k: int = 6) -> list[RetrievedChunk]:
    """Rank persisted chunks by cosine similarity to `question`. Returns an
    empty list if no index has been built yet -- callers should instruct the
    user to run `devtools index build --rag <project>` first, same pattern
    as `search_engine.semantic_search`'s `used_semantic` flag."""
    with _connect(project_name) as conn:
        rows = conn.execute("SELECT path, chunk_index, start_line, end_line, content, terms FROM chunks").fetchall()

    if not rows:
        return []

    doc_freq: Counter[str] = Counter()
    parsed = []
    for path, chunk_index, start_line, end_line, content, terms_json in rows:
        weights = _json.loads(terms_json)
        doc_freq.update(weights.keys())
        parsed.append((path, chunk_index, start_line, end_line, content, weights))

    query_vec = _query_vector(question, doc_freq, num_chunks=len(parsed))
    if not query_vec:
        return []

    scored = [
        RetrievedChunk(
            rel_path=path,
            chunk_index=chunk_index,
            start_line=start_line,
            end_line=end_line,
            content=content,
            score=round(_cosine_similarity(query_vec, weights), 4),
        )
        for path, chunk_index, start_line, end_line, content, weights in parsed
    ]
    scored = [c for c in scored if c.score > 0]
    scored.sort(key=lambda c: c.score, reverse=True)
    return scored[:top_k]


def generate_answer(question: str, chunks: list[RetrievedChunk], client: LLMClient) -> str:
    """Ask `client` to answer `question`, grounded only in the given
    (already-retrieved) chunks. Split out from `ask()` so callers -- like
    the `devtools ask` command -- can check whether the index returned
    anything *before* requiring an AI provider to be configured, the same
    "deterministic first, AI opt-in on top" order every other AI-flavored
    command follows."""
    blocks = [
        f"[{i}] `{c.rel_path}` (lines {c.start_line}-{c.end_line})\n```\n{c.content}\n```"
        for i, c in enumerate(chunks, start=1)
    ]
    prompt = f"Question: {question}\n\nRetrieved excerpts:\n\n" + "\n\n".join(blocks)
    return client.complete(prompt, system=_SYSTEM_PROMPT)


def ask(project_name: str, question: str, client: LLMClient, top_k: int = 6) -> RagAnswer:
    """Retrieve the top-k relevant chunks from the persistent index and ask
    `client` to answer `question` grounded in them."""
    chunks = retrieve(project_name, question, top_k=top_k)
    if not chunks:
        return RagAnswer(
            answer=(
                "No RAG index found (or nothing matched) for this project. "
                "Run `devtools index build --rag <project>` first, then ask again."
            ),
            sources=[],
            used_index=False,
        )

    answer_text = generate_answer(question, chunks, client)
    return RagAnswer(answer=answer_text, sources=chunks, used_index=True)
