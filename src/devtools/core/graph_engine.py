"""`devtools graph` — internal module dependency graph (backlog #7/#29, P1).

Python-only and AST-based, same policy as `complexity_engine`: only analyze
what can be done properly rather than approximate other languages. Unlike
`deps_engine` (which lists *external* manifest dependencies), this builds
a graph of the project's *own* modules importing each other -- the
"architecture at a glance" view: which packages are actually coupled,
where a change is going to ripple, what the real (as opposed to intended)
layering looks like.

Only imports that resolve to another file inside the scanned project
become edges; stdlib/third-party imports are silently dropped, since
those aren't part of *this* project's internal architecture and
`deps`/`sbom` already cover external dependencies.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

from devtools.core.filesystem import read_text_safely
from devtools.core.ignore_rules import IgnoreRules
from devtools.core.scanner import scan_project


@dataclass
class GraphEdge:
    source: str
    target: str


@dataclass
class DependencyGraph:
    nodes: list[str] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)

    def fan_in(self) -> dict[str, int]:
        """How many other internal modules import each node -- a rough
        "how risky is this to change" signal, same spirit as `hotspots`."""
        counts = dict.fromkeys(self.nodes, 0)
        for e in self.edges:
            if e.target in counts:
                counts[e.target] += 1
        return counts

    def to_mermaid(self) -> str:
        lines = ["graph LR"]
        for e in self.edges:
            lines.append(f'    {_mermaid_id(e.source)}["{e.source}"] --> {_mermaid_id(e.target)}["{e.target}"]')
        if not self.edges:
            for n in self.nodes:
                lines.append(f'    {_mermaid_id(n)}["{n}"]')
        return "\n".join(lines)

    def to_dot(self) -> str:
        lines = ["digraph devtools_graph {", '    rankdir="LR";']
        for n in self.nodes:
            lines.append(f'    "{n}";')
        for e in self.edges:
            lines.append(f'    "{e.source}" -> "{e.target}";')
        lines.append("}")
        return "\n".join(lines)


def _mermaid_id(dotted: str) -> str:
    """Mermaid node IDs can't contain dots; the human-readable name still
    goes in the `["..."]` label."""
    return dotted.replace(".", "_").replace("/", "_").replace("-", "_")


def _strip_src_root(rel_path: str) -> str:
    """Strip a leading `src/` -- the near-universal src-layout convention
    (this project included: `src/devtools/...` is imported as
    `devtools...`, not `src.devtools...`). Only the single, well-known
    `src/` root is special-cased rather than trying to detect arbitrary
    package roots, which would require actually resolving `pyproject.toml`
    packaging config -- not worth the complexity for a "good enough
    architecture view" tool.
    """
    return rel_path.removeprefix("src/")


def _module_name(rel_path: str) -> str:
    """"src/devtools/core/graph_engine.py" -> "devtools.core.graph_engine";
    an `__init__.py` names its *package*, not itself: "src/devtools/__init__.py" -> "devtools"."""
    stem = _strip_src_root(rel_path)
    stem = stem.removesuffix(".py")
    parts = stem.split("/")
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _package_parts(rel_path: str) -> list[str]:
    """Dotted parts of the *directory* containing this file -- the base
    for resolving `from . import x` / `from .. import y` relative imports,
    regardless of whether this file is itself a package's `__init__.py`."""
    stem = _strip_src_root(rel_path)
    directory = stem.rsplit("/", 1)[0] if "/" in stem else ""
    return directory.split("/") if directory else []


def _extract_imports(tree: ast.AST, rel_path: str) -> list[str]:
    """Every dotted target this file imports, already resolved to an
    absolute dotted path (relative imports walked up per their `level`)."""
    pkg_parts = _package_parts(rel_path)
    targets: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                targets.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                # level=1 means "this file's own package"; each extra level
                # walks one more directory up.
                base = pkg_parts[: len(pkg_parts) - (node.level - 1)] if node.level > 1 else pkg_parts
                base = base if node.level <= len(pkg_parts) + 1 else []
                if node.module:
                    targets.append(".".join([*base, node.module]))
                else:
                    for alias in node.names:
                        targets.append(".".join([*base, alias.name]))
            elif node.module:
                targets.append(node.module)
    return targets


def build_dependency_graph(root: Path, ignore_rules: IgnoreRules, module_prefix: str | None = None) -> DependencyGraph:
    """Scan every Python file, map it to a dotted module name, and draw an
    edge for each import that resolves to another module in that same set.

    `module_prefix` restricts *both* the nodes and edges shown to modules
    starting with that prefix (e.g. "devtools.core") -- an edge to/from a
    module outside the prefix is dropped along with the out-of-scope node,
    trading "show everything this subset touches" for a predictable,
    self-contained subgraph.
    """
    files: dict[str, str] = {}  # module name -> rel_path
    parsed: dict[str, ast.AST] = {}
    for entry in scan_project(root, ignore_rules, languages=["python"]):
        text = read_text_safely(entry.path)
        if text is None:
            continue
        try:
            tree = ast.parse(text, filename=entry.rel_path)
        except SyntaxError:
            continue
        mod = _module_name(entry.rel_path)
        files[mod] = entry.rel_path
        parsed[mod] = tree

    known_modules = set(files)
    # Also register every ancestor package prefix as "known" so an import
    # of a package (not a specific submodule) still resolves, e.g. `import
    # devtools.core` resolving against a project that only has
    # `devtools.core.graph_engine` etc. as leaf modules.
    known_prefixes = set(known_modules)
    for mod in known_modules:
        parts = mod.split(".")
        for i in range(1, len(parts)):
            known_prefixes.add(".".join(parts[:i]))

    edges: list[GraphEdge] = []
    seen_edges: set[tuple[str, str]] = set()
    for mod, tree in parsed.items():
        for target in _extract_imports(tree, files[mod]):
            if target == mod:
                continue
            resolved = target if target in known_prefixes else None
            if resolved is None:
                continue
            key = (mod, resolved)
            if key in seen_edges:
                continue
            seen_edges.add(key)
            edges.append(GraphEdge(source=mod, target=resolved))

    nodes = sorted(known_modules)
    if module_prefix:
        nodes = [n for n in nodes if n == module_prefix or n.startswith(module_prefix + ".")]
        node_set = set(nodes)
        edges = [e for e in edges if e.source in node_set and e.target in node_set]

    return DependencyGraph(nodes=nodes, edges=edges)