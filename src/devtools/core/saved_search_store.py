"""Storage for named, re-runnable `devtools search` queries
(`devtools search --save name`, Prioritized Backlog: "Saved searches", P38).

A saved search remembers the project, concept, and whether `--semantic` was
requested, so `devtools search --load name` reproduces the exact same query
later without retyping it. Same flat JSON-store pattern used throughout
`core/` for small named-entry data (`alias_store.py`, `bookmark_store.py`).
"""

from __future__ import annotations

import json as _json
from dataclasses import dataclass
from pathlib import Path

try:
    import orjson
except ImportError:  # pragma: no cover
    orjson = None  # type: ignore[assignment]

from devtools.utils.paths import saved_searches_file_path


@dataclass
class SavedSearch:
    name: str
    project: str
    concept: str
    semantic: bool = False

    def to_dict(self) -> dict:
        return {"project": self.project, "concept": self.concept, "semantic": self.semantic}

    @staticmethod
    def from_dict(name: str, data: dict) -> "SavedSearch":
        return SavedSearch(
            name=name,
            project=data.get("project", ""),
            concept=data.get("concept", ""),
            semantic=bool(data.get("semantic", False)),
        )


def _dumps(obj) -> bytes:
    if orjson is not None:
        return orjson.dumps(obj, option=orjson.OPT_INDENT_2)
    return _json.dumps(obj, indent=2).encode("utf-8")


def _loads(data: bytes | str):
    if orjson is not None:
        return orjson.loads(data)
    return _json.loads(data)


def load_saved_searches(path: Path | None = None) -> dict[str, SavedSearch]:
    p = path or saved_searches_file_path()
    if not p.is_file():
        return {}
    raw = _loads(p.read_bytes())
    return {name: SavedSearch.from_dict(name, data) for name, data in raw.items()}


def save_saved_searches(searches: dict[str, SavedSearch], path: Path | None = None) -> Path:
    p = path or saved_searches_file_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(_dumps({name: s.to_dict() for name, s in searches.items()}))
    return p


def save_search(name: str, project: str, concept: str, semantic: bool = False, path: Path | None = None) -> dict[str, SavedSearch]:
    searches = load_saved_searches(path)
    searches[name] = SavedSearch(name=name, project=project, concept=concept, semantic=semantic)
    save_saved_searches(searches, path)
    return searches


def remove_saved_search(name: str, path: Path | None = None) -> bool:
    searches = load_saved_searches(path)
    if name not in searches:
        return False
    del searches[name]
    save_saved_searches(searches, path)
    return True
