"""Storage for workspace snapshots (`devtools snapshot save/restore/list/remove`,
backlog #32, P2): "save/restore open files, branch, and notes as a session."

devtools has no editor integration, so "open files" here means a
user-supplied list of paths worth remembering (`--file`, repeatable) --
the git branch is captured automatically since that's unambiguous and
free. Same flat JSON-store pattern as `bookmark_store.py`/`alias_store.py`.
"""

from __future__ import annotations

import json as _json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

try:
    import orjson
except ImportError:  # pragma: no cover
    orjson = None  # type: ignore[assignment]

from devtools.utils.paths import snapshots_file_path


class SnapshotError(RuntimeError):
    """Raised for duplicate/unknown snapshot names."""


@dataclass
class Snapshot:
    name: str
    project: str
    branch: str | None
    files: list[str] = field(default_factory=list)
    note: str = ""
    created_at: str = ""

    def to_dict(self) -> dict:
        return {
            "project": self.project,
            "branch": self.branch,
            "files": self.files,
            "note": self.note,
            "created_at": self.created_at,
        }

    @staticmethod
    def from_dict(name: str, data: dict) -> "Snapshot":
        return Snapshot(
            name=name,
            project=data.get("project", ""),
            branch=data.get("branch"),
            files=list(data.get("files", []) or []),
            note=data.get("note", "") or "",
            created_at=data.get("created_at", "") or "",
        )


def _dumps(obj) -> bytes:
    if orjson is not None:
        return orjson.dumps(obj, option=orjson.OPT_INDENT_2)
    return _json.dumps(obj, indent=2).encode("utf-8")


def _loads(data: bytes | str):
    if orjson is not None:
        return orjson.loads(data)
    return _json.loads(data)


def load_snapshots(path: Path | None = None) -> dict[str, Snapshot]:
    p = path or snapshots_file_path()
    if not p.is_file():
        return {}
    raw = _loads(p.read_bytes())
    return {name: Snapshot.from_dict(name, data) for name, data in raw.items()}


def save_snapshots(snapshots: dict[str, Snapshot], path: Path | None = None) -> Path:
    p = path or snapshots_file_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(_dumps({name: s.to_dict() for name, s in snapshots.items()}))
    return p


def save_snapshot(
    name: str,
    project: str,
    branch: str | None,
    files: list[str],
    note: str = "",
    path: Path | None = None,
) -> Snapshot:
    snapshots = load_snapshots(path)
    snapshot = Snapshot(
        name=name,
        project=project,
        branch=branch,
        files=files,
        note=note,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    snapshots[name] = snapshot
    save_snapshots(snapshots, path)
    return snapshot


def remove_snapshot(name: str, path: Path | None = None) -> bool:
    snapshots = load_snapshots(path)
    if name not in snapshots:
        return False
    del snapshots[name]
    save_snapshots(snapshots, path)
    return True
