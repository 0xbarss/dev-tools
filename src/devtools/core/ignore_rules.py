"""Shared .gitignore-style ignore matching.

Used by collect, bundle, grep, tree, and stats so ignore behavior never
diverges between commands. Combines, in order of increasing precedence:

    1. built-in default ignored_dirs (from config.toml `ignored_dirs`)
    2. the repo's own .gitignore (unless --no-gitignore)
    3. project-level overrides (config.toml [project_overrides.<name>])
    4. ad-hoc --exclude globs passed on the command line

Implemented on top of `pathspec` (GitWildMatchPattern) so patterns behave
the way users expect from .gitignore syntax.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pathspec


@dataclass
class IgnoreRules:
    root: Path
    patterns: list[str] = field(default_factory=list)
    _spec: pathspec.PathSpec = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._spec = pathspec.PathSpec.from_lines("gitwildmatch", self.patterns)

    @classmethod
    def build(
        cls,
        root: Path,
        base_ignored_dirs: list[str],
        project_ignored_dirs: list[str] | None = None,
        extra_excludes: list[str] | None = None,
        use_gitignore: bool = True,
    ) -> "IgnoreRules":
        patterns: list[str] = []

        # 1. built-in / global ignored dirs (config.toml `ignored_dirs`)
        for d in base_ignored_dirs:
            patterns.append(_as_dir_pattern(d))

        # 2. the repo's own .gitignore
        if use_gitignore:
            gitignore = root / ".gitignore"
            if gitignore.is_file():
                patterns.extend(
                    line.rstrip("\n")
                    for line in gitignore.read_text(errors="ignore").splitlines()
                    if line.strip() and not line.strip().startswith("#")
                )

        # 3. project-level overrides
        for d in project_ignored_dirs or []:
            patterns.append(_as_dir_pattern(d))

        # 4. ad-hoc CLI --exclude globs (highest precedence, always appended last)
        for pat in extra_excludes or []:
            patterns.append(pat)

        # .git is always ignored, non-negotiably
        patterns.append(".git/")

        return cls(root=root, patterns=patterns)

    def is_ignored(self, path: Path) -> bool:
        try:
            rel = path.relative_to(self.root)
        except ValueError:
            rel = path
        rel_str = rel.as_posix()
        if path.is_dir():
            rel_str += "/"
        return self._spec.match_file(rel_str)

    def filtered_walk(self):
        """Yield non-ignored file Paths under root, pruning ignored directories."""
        stack = [self.root]
        while stack:
            current = stack.pop()
            try:
                entries = sorted(current.iterdir(), key=lambda p: p.name)
            except (PermissionError, FileNotFoundError):
                continue
            for entry in entries:
                if entry.is_symlink() and not entry.exists():
                    continue  # broken symlink, skip silently here (doctor reports these)
                if self.is_ignored(entry):
                    continue
                if entry.is_dir():
                    stack.append(entry)
                else:
                    yield entry


def _as_dir_pattern(d: str) -> str:
    d = d.strip().strip("/")
    if not d:
        return d
    # bare directory names should match anywhere in the tree, like .gitignore does
    return f"**/{d}/" if "/" not in d else f"{d}/"