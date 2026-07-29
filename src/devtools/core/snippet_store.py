"""Storage for small, reusable code snippets (`devtools snippet`,
Prioritized Backlog: "Snippet manager", P3).

Deliberately global (not per-project) -- these are meant to be the little
boilerplate fragments a developer reaches for across every repo (a logging
setup, a retry decorator, a shebang), not project-scoped data. Same flat
JSON-store pattern as `alias_store.py`/`bookmark_store.py`.
"""

from __future__ import annotations

import json as _json
from dataclasses import dataclass, field
from pathlib import Path

try:
    import orjson
except ImportError:  # pragma: no cover
    orjson = None  # type: ignore[assignment]

from devtools.utils.paths import snippets_file_path


@dataclass
class Snippet:
    name: str
    content: str
    language: str = ""
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"content": self.content, "language": self.language, "tags": self.tags}

    @staticmethod
    def from_dict(name: str, data: dict) -> "Snippet":
        return Snippet(
            name=name,
            content=data.get("content", ""),
            language=data.get("language", "") or "",
            tags=list(data.get("tags", []) or []),
        )


def _dumps(obj) -> bytes:
    if orjson is not None:
        return orjson.dumps(obj, option=orjson.OPT_INDENT_2)
    return _json.dumps(obj, indent=2).encode("utf-8")


def _loads(data: bytes | str):
    if orjson is not None:
        return orjson.loads(data)
    return _json.loads(data)


def load_snippets(path: Path | None = None) -> dict[str, Snippet]:
    p = path or snippets_file_path()
    if not p.is_file():
        return {}
    raw = _loads(p.read_bytes())
    return {name: Snippet.from_dict(name, data) for name, data in raw.items()}


def save_snippets(snippets: dict[str, Snippet], path: Path | None = None) -> Path:
    p = path or snippets_file_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(_dumps({name: s.to_dict() for name, s in snippets.items()}))
    return p


def add_snippet(
    name: str, content: str, language: str = "", tags: list[str] | None = None, path: Path | None = None
) -> dict[str, Snippet]:
    snippets = load_snippets(path)
    snippets[name] = Snippet(name=name, content=content, language=language, tags=tags or [])
    save_snippets(snippets, path)
    return snippets


def remove_snippet(name: str, path: Path | None = None) -> bool:
    snippets = load_snippets(path)
    if name not in snippets:
        return False
    del snippets[name]
    save_snippets(snippets, path)
    return True


def search_snippets(query: str, path: Path | None = None) -> list[Snippet]:
    """Case-insensitive match against name, tags, or content -- deliberately
    simple substring search; this is a small personal library, not `search`."""
    query_lower = query.lower()
    hits = []
    for snippet in load_snippets(path).values():
        haystack = " ".join([snippet.name, snippet.language, snippet.content, " ".join(snippet.tags)]).lower()
        if query_lower in haystack:
            hits.append(snippet)
    return sorted(hits, key=lambda s: s.name)
