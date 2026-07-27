"""Language detection and directory scanning built on top of ignore_rules."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from devtools.core.filesystem import FileEntry, iter_file_entries
from devtools.core.ignore_rules import IgnoreRules

# Extension -> language label. Intentionally covers the languages named in
# the `deps` command (§6) plus common general-purpose/web/config languages.
EXTENSION_LANGUAGE_MAP: dict[str, str] = {
    ".py": "python", ".pyi": "python", ".pyx": "python",
    ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript", ".cjs": "javascript",
    ".ts": "typescript", ".tsx": "typescript",
    ".rs": "rust",
    ".go": "go",
    ".java": "java", ".kt": "kotlin", ".kts": "kotlin",
    ".dart": "flutter",
    ".rb": "ruby",
    ".php": "php",
    ".c": "c", ".h": "c",
    ".cpp": "cpp", ".cc": "cpp", ".cxx": "cpp", ".hpp": "cpp",
    ".cs": "csharp",
    ".swift": "swift",
    ".sh": "shell", ".bash": "shell", ".zsh": "shell",
    ".sql": "sql",
    ".html": "html", ".htm": "html",
    ".css": "css", ".scss": "css", ".sass": "css", ".less": "css",
    ".json": "json",
    ".yaml": "yaml", ".yml": "yaml",
    ".toml": "toml",
    ".md": "markdown", ".mdx": "markdown",
    ".xml": "xml",
    ".dockerfile": "docker",
}

LANGUAGE_ALIASES: dict[str, str] = {
    "js": "javascript", "ts": "typescript", "py": "python",
    "rb": "ruby", "kt": "kotlin", "sh": "shell", "yml": "yaml", "md": "markdown",
}


def detect_language(path: Path) -> str:
    if path.name.lower() == "dockerfile":
        return "docker"
    ext = path.suffix.lower()
    return EXTENSION_LANGUAGE_MAP.get(ext, "other")


def normalize_lang(lang: str) -> str:
    lang = lang.strip().lower()
    return LANGUAGE_ALIASES.get(lang, lang)


def scan_project(
    root: Path,
    ignore_rules: IgnoreRules,
    languages: list[str] | None = None,
    parallel: bool = True,
    max_workers: int = 8,
) -> Iterator[FileEntry]:
    """Yield FileEntry objects for non-ignored files, optionally filtered by language.

    `parallel` controls whether the per-file stat + binary-sniff work (the
    actual I/O cost once the directory walk has produced candidate paths) is
    fanned out across a thread pool. Defaults to on; pass `parallel=False`
    for deterministic single-threaded behavior (e.g. in tests).
    """
    wanted = {normalize_lang(l) for l in languages} if languages else None

    def _paths() -> Iterator[Path]:
        for p in ignore_rules.filtered_walk():
            if wanted is not None and detect_language(p) not in wanted:
                continue
            yield p

    yield from iter_file_entries(_paths(), root, parallel=parallel, max_workers=max_workers)