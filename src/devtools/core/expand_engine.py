"""`devtools expand <source> <target>` — the inverse of `collect`: parses a
file previously produced by `devtools collect` (markdown, json, or text —
same three formats `core/collector.py` renders) and writes each collected
file back out to disk under `target`, recreating a real, usable project
directory from it.

Format is auto-detected from the file extension (`.md`/`.markdown` ->
markdown, `.json` -> json, anything else -> text) unless overridden.
Parsing deliberately mirrors each render_* function's exact output shape
(see `core/collector.py`) rather than trying to be a general-purpose
"any markdown with code fences" parser -- round-tripping devtools' own
output correctly matters far more than parsing arbitrary third-party
documents.

Markdown parsing note: a file's own content can itself contain a bare
``` ``` `` line (e.g. a collected README that has code fences in it), so a
naive "read until the first closing fence" parser breaks on exactly the
kind of file this command needs to handle. Instead, each file's block is
bounded by the *next* `## `path`` header (or EOF) and the closing fence is
taken as the **last** bare ``` ``` `` line in that block -- correctly
skipping over any fences nested inside the file's own content, and
correctly dropping the trailing "## Skipped (binary)" / "## Skipped (too
large)" sections `render_markdown` appends after the last real file.
"""

from __future__ import annotations

import json as _json
import re
from dataclasses import dataclass, field
from pathlib import Path

_HEADER_RE = re.compile(r"^## `([^`]+)`\s*$")


@dataclass
class ParsedFile:
    rel_path: str
    content: str


@dataclass
class ExpandResult:
    written: list[str] = field(default_factory=list)
    skipped_existing: list[str] = field(default_factory=list)
    target: Path = field(default_factory=Path)


class ExpandParseError(ValueError):
    """Raised when `source` doesn't look like valid collect output."""


class UnsafePathError(ValueError):
    """Raised when a parsed path would escape the target directory."""


def detect_format(path: Path, content: str) -> str:
    suffix = path.suffix.lower()
    if suffix in (".md", ".markdown"):
        return "markdown"
    if suffix == ".json":
        return "json"
    if suffix == ".txt":
        return "text"
    # Sniff: collect's markdown always has at least one `## `path`` header;
    # its json is a top-level object; anything else falls back to text.
    stripped = content.lstrip()
    if stripped.startswith("{"):
        return "json"
    if _HEADER_RE.search(content) is not None or re.search(r"^## `", content, re.MULTILINE):
        return "markdown"
    return "text"


def parse_markdown(content: str) -> list[ParsedFile]:
    lines = content.split("\n")
    n = len(lines)
    headers: list[tuple[int, str]] = []
    for idx, line in enumerate(lines):
        m = _HEADER_RE.match(line)
        if m:
            headers.append((idx, m.group(1)))

    if not headers:
        raise ExpandParseError("No `## `path`` file headers found -- doesn't look like `collect --format markdown` output.")

    files: list[ParsedFile] = []
    for hi, (idx, rel_path) in enumerate(headers):
        start = idx + 1
        end = headers[hi + 1][0] if hi + 1 < len(headers) else n
        block = lines[start:end]

        while block and block[0].strip() == "":
            block.pop(0)
        if block and block[0].startswith("```"):
            block.pop(0)
        else:
            continue  # not actually a file block (e.g. a "## Skipped" section slipped past the regex)

        # Closing fence = the LAST bare "```" line in the block, so any
        # fences nested inside the file's own content are preserved as
        # content rather than mistaken for the boundary.
        close_at = None
        for i in range(len(block) - 1, -1, -1):
            if block[i].strip() == "```":
                close_at = i
                break
        content_lines = block[:close_at] if close_at is not None else block

        files.append(ParsedFile(rel_path=rel_path, content="\n".join(content_lines)))

    if not files:
        raise ExpandParseError("Found file headers but no fenced content under any of them.")
    return files


def parse_json(content: str) -> list[ParsedFile]:
    try:
        data = _json.loads(content)
    except _json.JSONDecodeError as exc:
        raise ExpandParseError(f"Not valid JSON: {exc}") from exc

    raw_files = data.get("files") if isinstance(data, dict) else None
    if not isinstance(raw_files, list):
        raise ExpandParseError("Expected a top-level `files` list -- doesn't look like `collect --format json` output.")

    files = []
    for entry in raw_files:
        if not isinstance(entry, dict) or "path" not in entry or "content" not in entry:
            raise ExpandParseError("Each entry in `files` must have `path` and `content`.")
        files.append(ParsedFile(rel_path=entry["path"], content=entry["content"]))
    if not files:
        raise ExpandParseError("The `files` list is empty -- nothing to expand.")
    return files


_TEXT_HEADER_RE = re.compile(r"^-{5} (.+) -{5}$")


def parse_text(content: str) -> list[ParsedFile]:
    lines = content.split("\n")
    n = len(lines)
    headers: list[tuple[int, str]] = []
    for idx, line in enumerate(lines):
        m = _TEXT_HEADER_RE.match(line)
        if m:
            headers.append((idx, m.group(1)))

    if not headers:
        raise ExpandParseError("No `----- path -----` markers found -- doesn't look like `collect --format text` output.")

    files = []
    for hi, (idx, rel_path) in enumerate(headers):
        start = idx + 1
        end = headers[hi + 1][0] if hi + 1 < len(headers) else n
        body = lines[start:end]
        # render_text joins with "\n" and doesn't add a trailing blank
        # separator, so the last line of one file's body can butt directly
        # against the next header; drop one trailing empty line if present.
        if body and body[-1] == "" and hi + 1 < len(headers):
            body = body[:-1]
        files.append(ParsedFile(rel_path=rel_path, content="\n".join(body)))
    return files


def parse(content: str, fmt: str) -> list[ParsedFile]:
    if fmt == "markdown":
        return parse_markdown(content)
    if fmt == "json":
        return parse_json(content)
    if fmt == "text":
        return parse_text(content)
    raise ValueError(f"Unknown format: {fmt!r}")


def _validate_rel_path(rel_path: str) -> Path:
    p = Path(rel_path)
    if p.is_absolute() or ".." in p.parts:
        raise UnsafePathError(f"Refusing to write outside the target directory: {rel_path!r}")
    return p


def expand(
    source: Path,
    target: Path,
    fmt: str | None = None,
    force: bool = False,
) -> ExpandResult:
    """Parse `source` (a `collect`-produced file) and write each collected
    file into `target`, creating directories as needed.

    Safety: if any file we're about to write already exists on disk with
    *different* content, the whole operation is aborted before writing
    anything, unless `force=True` -- expanding into a directory you already
    have work in should never silently clobber it.
    """
    content = source.read_text(encoding="utf-8")
    resolved_fmt = fmt or detect_format(source, content)
    files = parse(content, resolved_fmt)

    target = target.expanduser()
    conflicts: list[str] = []
    plan: list[tuple[Path, ParsedFile]] = []
    for f in files:
        rel = _validate_rel_path(f.rel_path)
        full = target / rel
        plan.append((full, f))
        if full.is_file():
            existing = full.read_text(encoding="utf-8", errors="replace")
            if existing != f.content:
                conflicts.append(f.rel_path)

    if conflicts and not force:
        raise FileExistsError(
            f"{len(conflicts)} file(s) already exist with different content (use --force to overwrite): "
            + ", ".join(conflicts[:5])
            + (", ..." if len(conflicts) > 5 else "")
        )

    result = ExpandResult(target=target)
    for full, f in plan:
        if full.is_file():
            existing = full.read_text(encoding="utf-8", errors="replace")
            if existing == f.content:
                result.skipped_existing.append(f.rel_path)
                continue
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(f.content, encoding="utf-8")
        result.written.append(f.rel_path)

    return result
