"""Shared collection + AI-ready formatting logic for collect/bundle/context.

Kept here (rather than duplicated in each command module) so the three
commands stay byte-for-byte consistent in how they format a "file block",
per the golden-file testing strategy in spec §11.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from devtools.core.filesystem import read_text_safely
from devtools.core.ignore_rules import IgnoreRules
from devtools.core.scanner import detect_language, scan_project
from devtools.core.tokenizer import count_tokens

_PARALLEL_THRESHOLD = 64
_DEFAULT_MAX_WORKERS = 8


@dataclass
class CollectedFile:
    rel_path: str
    language: str
    content: str
    tokens: int
    size: int


@dataclass
class CollectionResult:
    root: Path
    files: list[CollectedFile] = field(default_factory=list)
    skipped_binary: list[str] = field(default_factory=list)
    skipped_too_large: list[str] = field(default_factory=list)
    truncated: bool = False

    @property
    def total_tokens(self) -> int:
        return sum(f.tokens for f in self.files)

    @property
    def total_size(self) -> int:
        return sum(f.size for f in self.files)


@dataclass
class _ReadResult:
    path: Path
    status: str  # "ok" | "binary" | "too_large"
    text: str | None = None
    tokens: int = 0


def _read_one(path: Path, max_size: int | None) -> _ReadResult:
    if max_size is not None:
        try:
            if path.stat().st_size > max_size:
                return _ReadResult(path=path, status="too_large")
        except OSError:
            return _ReadResult(path=path, status="too_large")

    text = read_text_safely(path, max_bytes=max_size)
    if text is None:
        return _ReadResult(path=path, status="binary")

    return _ReadResult(path=path, status="ok", text=text, tokens=count_tokens(text))


def collect_files(
    root: Path,
    ignore_rules: IgnoreRules,
    languages: list[str] | None = None,
    max_size: int | None = None,
    only_paths: list[Path] | None = None,
    max_tokens: int | None = None,
    parallel: bool = True,
    max_workers: int = _DEFAULT_MAX_WORKERS,
) -> CollectionResult:
    """Walk the project (or `only_paths`), reading and token-counting files.

    If `max_tokens` is given, files are appended in the order encountered
    until the budget would be exceeded; remaining files are noted as
    truncated (mirrors the `bundle --max-tokens` truncation behavior).

    Reading + tokenizing is fanned out over a thread pool (I/O-bound, so this
    parallelizes well) but the budget-enforcement pass afterward stays
    strictly sequential in encounter-order, since which files get truncated
    depends on that order — parallelizing the read must never change *which*
    files end up included.
    """
    result = CollectionResult(root=root)

    if only_paths is not None:
        entries = [p for p in only_paths if p.is_file() and not ignore_rules.is_ignored(p)]
    else:
        entries = [e.path for e in scan_project(root, ignore_rules, languages=languages, parallel=parallel, max_workers=max_workers)]

    if not parallel or len(entries) < _PARALLEL_THRESHOLD:
        reads = [_read_one(p, max_size) for p in entries]
    else:
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            reads = list(pool.map(lambda p: _read_one(p, max_size), entries))

    running_tokens = 0
    for r in reads:
        if r.status == "too_large":
            result.skipped_too_large.append(_rel(r.path, root))
            continue
        if r.status == "binary":
            result.skipped_binary.append(_rel(r.path, root))
            continue

        if max_tokens is not None and running_tokens + r.tokens > max_tokens:
            result.truncated = True
            continue

        running_tokens += r.tokens
        result.files.append(
            CollectedFile(
                rel_path=_rel(r.path, root),
                language=detect_language(r.path),
                content=r.text,
                tokens=r.tokens,
                size=len(r.text.encode("utf-8", errors="replace")),
            )
        )

    return result


def _rel(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def render_markdown(result: CollectionResult, project_name: str, title: str | None = None) -> str:
    lines: list[str] = [f"# {title or f'{project_name} — collected source'}", ""]
    lines.append(f"- Files: {len(result.files)}")
    lines.append(f"- Total tokens (approx.): {result.total_tokens}")
    lines.append(f"- Total size: {result.total_size} bytes")
    if result.truncated:
        lines.append("- **Truncated:** token budget exceeded, some files omitted")
    lines.append("")
    for f in result.files:
        lines.append(f"## `{f.rel_path}`")
        lines.append("")
        lines.append(f"```{f.language if f.language != 'other' else ''}")
        lines.append(f.content.rstrip("\n"))
        lines.append("```")
        lines.append("")
    if result.skipped_binary:
        lines.append("## Skipped (binary)")
        lines.extend(f"- {p}" for p in result.skipped_binary)
        lines.append("")
    if result.skipped_too_large:
        lines.append("## Skipped (too large)")
        lines.extend(f"- {p}" for p in result.skipped_too_large)
        lines.append("")
    return "\n".join(lines)


def render_text(result: CollectionResult) -> str:
    parts = []
    for f in result.files:
        parts.append(f"----- {f.rel_path} -----")
        parts.append(f.content)
    return "\n".join(parts)


def render_json(result: CollectionResult) -> dict:
    return {
        "root": str(result.root),
        "file_count": len(result.files),
        "total_tokens": result.total_tokens,
        "total_size": result.total_size,
        "truncated": result.truncated,
        "files": [
            {
                "path": f.rel_path,
                "language": f.language,
                "tokens": f.tokens,
                "size": f.size,
                "content": f.content,
            }
            for f in result.files
        ],
        "skipped_binary": result.skipped_binary,
        "skipped_too_large": result.skipped_too_large,
    }


def chunk_by_tokens(files: list[CollectedFile], chunk_size: int) -> list[list[CollectedFile]]:
    """Split files into groups whose summed token count stays under chunk_size.

    A single file larger than chunk_size becomes its own chunk (never split
    mid-file — that would break the "valid standalone markdown" goal in §9).
    """
    chunks: list[list[CollectedFile]] = []
    current: list[CollectedFile] = []
    current_tokens = 0
    for f in files:
        if current and current_tokens + f.tokens > chunk_size:
            chunks.append(current)
            current, current_tokens = [], 0
        current.append(f)
        current_tokens += f.tokens
    if current:
        chunks.append(current)
    return chunks