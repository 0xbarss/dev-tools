"""Append-only history log (~/.config/devtools/history.jsonl).

One JSON object per line: {"ts", "cmd", "project", "duration_ms", "exit_code"}.
Kept append-only and line-oriented so it stays cheap to write to on every
invocation and cheap to tail for `history --last N` without loading the
whole file when it's small, while still being simple to scan in full.
"""

from __future__ import annotations

import json as _json
from collections.abc import Iterator
from pathlib import Path

try:
    import orjson
except ImportError:  # pragma: no cover
    orjson = None  # type: ignore[assignment]

from devtools.utils.helpers import utc_now_iso
from devtools.utils.paths import history_file_path


def _dumps(obj: dict) -> str:
    if orjson is not None:
        return orjson.dumps(obj).decode("utf-8")
    return _json.dumps(obj)


def record_run(
    cmd: str,
    project: str | None,
    duration_ms: int,
    exit_code: int,
    log_path: Path | None = None,
) -> None:
    path = log_path or history_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": utc_now_iso(),
        "cmd": cmd,
        "project": project,
        "duration_ms": duration_ms,
        "exit_code": exit_code,
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(_dumps(entry) + "\n")


def iter_entries(log_path: Path | None = None) -> Iterator[dict]:
    path = log_path or history_file_path()
    if not path.is_file():
        return
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield _json.loads(line)
            except ValueError:
                continue  # skip a corrupted line rather than fail the whole read


def read_entries(
    log_path: Path | None = None,
    project: str | None = None,
    last: int | None = None,
) -> list[dict]:
    entries = list(iter_entries(log_path))
    if project:
        entries = [e for e in entries if e.get("project") == project]
    if last:
        entries = entries[-last:]
    return entries


class run_timer:
    """Context manager used by cli.py to wrap every command invocation.

    Usage:
        with run_timer() as t:
            ... run the command ...
        record_run(cmd_name, project, t.duration_ms, exit_code)
    """

    def __init__(self) -> None:
        self.duration_ms = 0
        self._start = 0.0

    def __enter__(self) -> "run_timer":
        import time

        self._start = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        import time

        self.duration_ms = int((time.perf_counter() - self._start) * 1000)
