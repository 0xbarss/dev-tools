"""Filesystem helpers shared across commands.

Kept iterative/streaming (no full-tree loads into memory) per the
"Fast on large repos" goal in §1 of the spec: callers get generators, not lists,
wherever the underlying operation can be a generator.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

# Below this many candidate paths, threading overhead isn't worth it —
# matches the "don't add complexity that doesn't pay for itself" philosophy
# used elsewhere (e.g. is_probably_binary's simple byte-ratio heuristic).
_PARALLEL_THRESHOLD = 64
_DEFAULT_MAX_WORKERS = 8


@dataclass
class FileEntry:
    path: Path
    rel_path: str
    size: int
    mtime: float
    is_binary: bool


def is_probably_binary(path: Path, sniff_bytes: int = 8192) -> bool:
    try:
        with path.open("rb") as f:
            chunk = f.read(sniff_bytes)
    except OSError:
        return True
    if b"\x00" in chunk:
        return True
    # Heuristic: a high proportion of non-text bytes implies binary content.
    text_chars = bytes(range(32, 127)) + b"\n\r\t\b\f"
    nontext = sum(b not in text_chars for b in chunk)
    return bool(chunk) and (nontext / len(chunk)) > 0.30


def _build_entry(p: Path, root: Path) -> FileEntry | None:
    try:
        stat = p.stat()
    except OSError:
        return None
    return FileEntry(
        path=p,
        rel_path=p.relative_to(root).as_posix(),
        size=stat.st_size,
        mtime=stat.st_mtime,
        is_binary=is_probably_binary(p),
    )


def iter_file_entries(
    paths: Iterator[Path],
    root: Path,
    parallel: bool = True,
    max_workers: int = _DEFAULT_MAX_WORKERS,
) -> Iterator[FileEntry]:
    """Yield a FileEntry per path.

    Each entry requires a stat() call plus a small read for binary sniffing —
    pure I/O, so it parallelizes well with threads despite the GIL. Below
    `_PARALLEL_THRESHOLD` paths we just go serial: thread-pool setup isn't
    worth it for a handful of files, and this keeps single-file/tiny-repo
    commands from paying pool-creation overhead for nothing.
    """
    path_list = list(paths)
    if not parallel or len(path_list) < _PARALLEL_THRESHOLD:
        for p in path_list:
            entry = _build_entry(p, root)
            if entry is not None:
                yield entry
        return

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        for entry in pool.map(lambda p: _build_entry(p, root), path_list):
            if entry is not None:
                yield entry


def read_text_safely(path: Path, max_bytes: int | None = None) -> str | None:
    """Read a file as text, returning None if it looks binary or is unreadable."""
    try:
        if max_bytes is not None and path.stat().st_size > max_bytes:
            return None
        if is_probably_binary(path):
            return None
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def file_hash(path: Path, algo: str = "sha256", chunk_size: int = 65536) -> str | None:
    h = hashlib.new(algo)
    try:
        with path.open("rb") as f:
            while chunk := f.read(chunk_size):
                h.update(chunk)
    except OSError:
        return None
    return h.hexdigest()


def dir_size(path: Path) -> int:
    total = 0
    for dirpath, _dirnames, filenames in os.walk(path):
        for name in filenames:
            fp = Path(dirpath) / name
            try:
                total += fp.stat().st_size
            except OSError:
                continue
    return total


def safe_relative(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)