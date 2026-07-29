"""Cyclomatic complexity metrics for Python source (proposal #14).

Pure computation, no rendering — this only produces structured
`FileComplexity`/`FunctionComplexity` data so the future `health` (#13) and
`hotspots` (#10) commands can consume it directly once they exist, the same
way `doctor_checks` already reuses `stats_engine.find_duplicate_files`.

Only Python is supported today (this is AST-based); other languages are
silently skipped rather than approximated, matching `lint_engine`'s policy
of only running analysis it can actually do properly.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

from devtools.core.filesystem import read_text_safely
from devtools.core.ignore_rules import IgnoreRules
from devtools.core.scanner import scan_project

# Cyclomatic complexity starts at 1 (one linear path through the function);
# each of these node types adds one additional independent path/branch.
_DECISION_NODES = (
    ast.If,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.Try,
    ast.ExceptHandler,
    ast.With,
    ast.AsyncWith,
    ast.Assert,
    ast.comprehension,
)


@dataclass
class FunctionComplexity:
    name: str
    qualname: str
    lineno: int
    complexity: int


@dataclass
class FileComplexity:
    rel_path: str
    functions: list[FunctionComplexity] = field(default_factory=list)

    @property
    def total_complexity(self) -> int:
        return sum(f.complexity for f in self.functions)

    @property
    def max_complexity(self) -> int:
        return max((f.complexity for f in self.functions), default=0)


class _ComplexityVisitor(ast.NodeVisitor):
    """Counts branch points inside a single function body.

    Deliberately does not descend into nested function/class definitions —
    those are scored separately (via `_iter_functions`) so a nested helper's
    branches aren't double-counted against its enclosing function.
    """

    def __init__(self) -> None:
        self.complexity = 1

    def visit_FunctionDef(self, node: ast.AST) -> None:  # noqa: N802 - ast API name
        return  # scored independently by the outer walk

    def visit_AsyncFunctionDef(self, node: ast.AST) -> None:  # noqa: N802
        return

    def visit_ClassDef(self, node: ast.AST) -> None:  # noqa: N802
        return

    def generic_visit(self, node: ast.AST) -> None:
        if isinstance(node, _DECISION_NODES):
            self.complexity += 1
        elif isinstance(node, ast.BoolOp):
            # `a and b and c` short-circuits, adding len(values) - 1 paths.
            self.complexity += len(node.values) - 1
        elif isinstance(node, ast.IfExp):
            self.complexity += 1
        super().generic_visit(node)


def _score_function(node: ast.AST) -> int:
    visitor = _ComplexityVisitor()
    for child in ast.iter_child_nodes(node):
        visitor.visit(child)
    return visitor.complexity


def _iter_functions(tree: ast.AST, prefix: str = ""):
    """Yield (node, qualname) for every function/method at any nesting depth."""
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            qualname = f"{prefix}{node.name}"
            yield node, qualname
            yield from _iter_functions(node, prefix=f"{qualname}.")
        elif isinstance(node, ast.ClassDef):
            yield from _iter_functions(node, prefix=f"{prefix}{node.name}.")


def compute_file_complexity(path: Path, rel_path: str) -> FileComplexity | None:
    """Compute per-function complexity for a single Python file.

    Returns None (rather than an empty result) for unreadable/binary files
    or files that don't parse as valid Python, so callers can distinguish
    "nothing to report" from "couldn't analyze this one".
    """
    text = read_text_safely(path)
    if text is None:
        return None
    try:
        tree = ast.parse(text, filename=rel_path)
    except SyntaxError:
        return None

    functions = [
        FunctionComplexity(name=node.name, qualname=qualname, lineno=node.lineno, complexity=_score_function(node))
        for node, qualname in _iter_functions(tree)
    ]
    return FileComplexity(rel_path=rel_path, functions=functions)


def compute_complexity(root: Path, ignore_rules: IgnoreRules) -> list[FileComplexity]:
    """Compute per-function cyclomatic complexity for every Python file in the project.

    Files with no functions (pure config/data, `__init__.py` re-exports,
    etc.) are omitted from the result entirely.
    """
    results: list[FileComplexity] = []
    for entry in scan_project(root, ignore_rules, languages=["python"]):
        fc = compute_file_complexity(entry.path, entry.rel_path)
        if fc is not None and fc.functions:
            results.append(fc)
    return results