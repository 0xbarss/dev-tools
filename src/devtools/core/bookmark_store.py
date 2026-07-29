"""Storage for named bookmarks (`devtools bookmark add/list/remove/go`,
Prioritized Backlog: "Bookmarks", P3).

A bookmark is a named quick-jump to a path within a registered project --
useful for "the file I keep coming back to" without remembering the full
relative path. Same flat JSON-store pattern as `alias_store.py` /
`notify_engine.py`, so it needs no new dependencies and is trivially
unit-testable.
"""

from __future__ import annotations

import json as _json
from dataclasses import dataclass
from pathlib import Path

try:
    import orjson
except ImportError:  # pragma: no cover
    orjson = None  # type: ignore[assignment]

from devtools.utils.paths import bookmarks_file_path


class BookmarkError(RuntimeError):
    """Raised for duplicate/unknown bookmark names."""


@dataclass
class Bookmark:
    name: str
    project: str
    path: str  # relative path (posix-style) within the project
    note: str = ""

    def to_dict(self) -> dict:
        return {"project": self.project, "path": self.path, "note": self.note}

    @staticmethod
    def from_dict(name: str, data: dict) -> "Bookmark":
        return Bookmark(name=name, project=data.get("project", ""), path=data.get("path", ""), note=data.get("note", "") or "")


def _dumps(obj) -> bytes:
    if orjson is not None:
        return orjson.dumps(obj, option=orjson.OPT_INDENT_2)
    return _json.dumps(obj, indent=2).encode("utf-8")


def _loads(data: bytes | str):
    if orjson is not None:
        return orjson.loads(data)
    return _json.loads(data)


def load_bookmarks(path: Path | None = None) -> dict[str, Bookmark]:
    p = path or bookmarks_file_path()
    if not p.is_file():
        return {}
    raw = _loads(p.read_bytes())
    return {name: Bookmark.from_dict(name, data) for name, data in raw.items()}


def save_bookmarks(bookmarks: dict[str, Bookmark], path: Path | None = None) -> Path:
    p = path or bookmarks_file_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(_dumps({name: b.to_dict() for name, b in bookmarks.items()}))
    return p


def add_bookmark(name: str, project: str, rel_path: str, note: str = "", path: Path | None = None) -> dict[str, Bookmark]:
    bookmarks = load_bookmarks(path)
    bookmarks[name] = Bookmark(name=name, project=project, path=rel_path, note=note)
    save_bookmarks(bookmarks, path)
    return bookmarks


def remove_bookmark(name: str, path: Path | None = None) -> bool:
    bookmarks = load_bookmarks(path)
    if name not in bookmarks:
        return False
    del bookmarks[name]
    save_bookmarks(bookmarks, path)
    return True
