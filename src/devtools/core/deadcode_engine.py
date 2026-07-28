"""Dead code detection (proposal #11): unused imports, and Python
module-level functions/classes that are defined but never referenced
anywhere else in the project.

This is deliberately "AST-lite" rather than a full call-graph/points-to
analysis (the kind of rigor tools like vulture/pyflakes bring): unused
imports are checked precisely via AST within their own file, but the
cross-file "is this ever used?" question is answered with a name-occurrence
scan across every file in the project — the same pragmatic, keyword-based
approach `grep_engine`/`search_engine` already use elsewhere in this
codebase, rather than a real symbol resolver.

Because of that, findings are leads, not proof: dynamic dispatch
(`getattr`, string-based routing), reflection, and framework-invoked
callbacks (routes, fixtures, signal handlers) can all still surface here as
false positives. Some well-known false-positive shapes are excluded by
default (dunder methods, decorated definitions, `test_*` functions); the
rest is left to the reader's judgment, same as `doctor`'s advisory findings.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path

from devtools.core.filesystem import read_text_safely
from devtools.core.ignore_rules import IgnoreRules
from devtools.core.scanner import scan_project

_DUNDER_RE = re.compile(r"^__.+__$")


@dataclass
class UnusedImport:
    rel_path: str
    lineno: int
    name: str


@dataclass
class UnusedDefinition:
    rel_path: str
    lineno: int
    kind: str  # "function" | "class"
    name: str


@dataclass
class DeadCodeReport:
    unused_imports: list[UnusedImport] = field(default_factory=list)
    unused_definitions: list[UnusedDefinition] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.unused_imports) + len(self.unused_definitions)


def _module_imports(tree: ast.Module) -> list[tuple[int, str]]:
    """Return (lineno, bound_name) for every name an import statement binds
    into the module namespace (aliases via `as`, star imports excluded —
    there's no way to know what a `*` import shadows without executing it)."""
    bindings: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                bound = alias.asname or alias.name.split(".")[0]
                bindings.append((node.lineno, bound))
        elif isinstance(node, ast.ImportFrom):
            if node.module == "__future__":
                continue  # compiler directives (e.g. `annotations`), never referenced by name
            for alias in node.names:
                if alias.name == "*":
                    continue
                bound = alias.asname or alias.name
                bindings.append((node.lineno, bound))
    return bindings


def find_unused_imports(path: Path, rel_path: str) -> list[UnusedImport]:
    """Imports bound in `path` that are never referenced as a bare name
    anywhere else in the same file (re-exports via `__all__` are respected)."""
    text = read_text_safely(path)
    if text is None:
        return []
    try:
        tree = ast.parse(text, filename=rel_path)
    except SyntaxError:
        return []

    imports = _module_imports(tree)
    if not imports:
        return []

    used: set[str] = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    exported = _all_exports(tree)

    unused = []
    for lineno, bound in imports:
        if _DUNDER_RE.match(bound):
            continue
        if bound in used or bound in exported:
            continue
        unused.append(UnusedImport(rel_path=rel_path, lineno=lineno, name=bound))
    return unused


def _all_exports(tree: ast.Module) -> set[str]:
    """Best-effort read of a module-level `__all__ = [...]`/`(...)` literal."""
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets):
            continue
        if isinstance(node.value, (ast.List, ast.Tuple, ast.Set)):
            return {elt.value for elt in node.value.elts if isinstance(elt, ast.Constant) and isinstance(elt.value, str)}
    return set()


def find_module_level_definitions(
    path: Path,
    rel_path: str,
    include_decorated: bool = False,
    include_tests: bool = False,
) -> list[UnusedDefinition]:
    """Every module-level (not nested inside a class/function) function or
    class definition in `path`, as a *candidate* — callers still need to
    check whether it's referenced anywhere in the project.

    Excluded by default: dunder methods, `test_*` functions (pytest finds
    these by discovery, not by reference), and decorated definitions
    (routes, fixtures, `@app.command()`, etc. are invoked by a framework,
    not by a visible call site, so they'd otherwise dominate the false
    positives).
    """
    text = read_text_safely(path)
    if text is None:
        return []
    try:
        tree = ast.parse(text, filename=rel_path)
    except SyntaxError:
        return []

    defs: list[UnusedDefinition] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if _DUNDER_RE.match(node.name):
                continue
            if not include_tests and node.name.startswith("test_"):
                continue
            if not include_decorated and node.decorator_list:
                continue
            defs.append(UnusedDefinition(rel_path=rel_path, lineno=node.lineno, kind="function", name=node.name))
        elif isinstance(node, ast.ClassDef):
            if not include_decorated and node.decorator_list:
                continue
            defs.append(UnusedDefinition(rel_path=rel_path, lineno=node.lineno, kind="class", name=node.name))
    return defs


def compute_deadcode(
    root: Path,
    ignore_rules: IgnoreRules,
    include_decorated: bool = False,
    include_tests: bool = False,
) -> DeadCodeReport:
    """Find unused imports (per-file, AST-exact) and unused module-level
    functions/classes (repo-wide name-occurrence scan, approximate).

    Known limitation: two module-level definitions sharing the same name in
    different files (e.g. two unrelated `main`s) can mask each other, since
    occurrence counting is name-based rather than symbol-resolved.
    """
    py_entries = list(scan_project(root, ignore_rules, languages=["python"]))

    unused_imports: list[UnusedImport] = []
    candidates: list[UnusedDefinition] = []
    for entry in py_entries:
        unused_imports.extend(find_unused_imports(entry.path, entry.rel_path))
        candidates.extend(
            find_module_level_definitions(
                entry.path, entry.rel_path, include_decorated=include_decorated, include_tests=include_tests
            )
        )

    if not candidates:
        return DeadCodeReport(unused_imports=unused_imports, unused_definitions=[])

    # Read every project file's text once up front (any language — a Python
    # symbol can legitimately be referenced from docs, configs, or scripts)
    # so each candidate's occurrence count is a regex scan over already-read
    # text, not a fresh disk read per candidate.
    texts: dict[str, str] = {}
    for entry in scan_project(root, ignore_rules):
        text = read_text_safely(entry.path)
        if text is not None:
            texts[entry.rel_path] = text

    unused_defs: list[UnusedDefinition] = []
    for d in candidates:
        pattern = re.compile(r"\b" + re.escape(d.name) + r"\b")
        occurrences = 0
        for rel_path, text in texts.items():
            count = len(pattern.findall(text))
            if rel_path == d.rel_path:
                count -= 1  # subtract the definition's own `def name`/`class name` occurrence
            occurrences += max(count, 0)
        if occurrences <= 0:
            unused_defs.append(d)

    return DeadCodeReport(unused_imports=unused_imports, unused_definitions=unused_defs)
