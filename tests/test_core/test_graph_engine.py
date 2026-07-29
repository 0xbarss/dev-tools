from __future__ import annotations

from devtools.core.graph_engine import build_dependency_graph, _module_name
from devtools.core.ignore_rules import IgnoreRules


def _rules(root):
    return IgnoreRules.build(root, base_ignored_dirs=["node_modules", "__pycache__"])


def _write(root, rel_path, content):
    p = root / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)


def test_module_name_handles_init_and_regular_files():
    assert _module_name("pkg/mod.py") == "pkg.mod"
    assert _module_name("pkg/__init__.py") == "pkg"
    assert _module_name("pkg/sub/__init__.py") == "pkg.sub"


def test_module_name_strips_conventional_src_layout_root():
    assert _module_name("src/pkg/mod.py") == "pkg.mod"
    assert _module_name("src/pkg/__init__.py") == "pkg"


def test_build_dependency_graph_absolute_import(tmp_path):
    _write(tmp_path, "pkg/__init__.py", "")
    _write(tmp_path, "pkg/a.py", "import pkg.b\n")
    _write(tmp_path, "pkg/b.py", "x = 1\n")

    graph = build_dependency_graph(tmp_path, _rules(tmp_path))
    assert "pkg.a" in graph.nodes and "pkg.b" in graph.nodes
    assert any(e.source == "pkg.a" and e.target == "pkg.b" for e in graph.edges)


def test_build_dependency_graph_relative_import_same_package(tmp_path):
    _write(tmp_path, "pkg/__init__.py", "")
    _write(tmp_path, "pkg/a.py", "from . import b\n")
    _write(tmp_path, "pkg/b.py", "x = 1\n")

    graph = build_dependency_graph(tmp_path, _rules(tmp_path))
    assert any(e.source == "pkg.a" and e.target == "pkg.b" for e in graph.edges)


def test_build_dependency_graph_relative_from_module_import(tmp_path):
    _write(tmp_path, "pkg/__init__.py", "")
    _write(tmp_path, "pkg/sub/__init__.py", "")
    _write(tmp_path, "pkg/sub/a.py", "from .. import b\n")
    _write(tmp_path, "pkg/b.py", "x = 1\n")

    graph = build_dependency_graph(tmp_path, _rules(tmp_path))
    assert any(e.source == "pkg.sub.a" and e.target == "pkg.b" for e in graph.edges)


def test_build_dependency_graph_drops_external_imports(tmp_path):
    _write(tmp_path, "pkg/__init__.py", "")
    _write(tmp_path, "pkg/a.py", "import os\nimport requests\n")

    graph = build_dependency_graph(tmp_path, _rules(tmp_path))
    assert graph.edges == []


def test_build_dependency_graph_module_prefix_filters_subgraph(tmp_path):
    _write(tmp_path, "pkg/__init__.py", "")
    _write(tmp_path, "pkg/core/__init__.py", "")
    _write(tmp_path, "pkg/core/a.py", "from pkg.core import b\nfrom pkg import outside\n")
    _write(tmp_path, "pkg/core/b.py", "x = 1\n")
    _write(tmp_path, "pkg/outside.py", "x = 1\n")

    graph = build_dependency_graph(tmp_path, _rules(tmp_path), module_prefix="pkg.core")
    assert all(n.startswith("pkg.core") for n in graph.nodes)
    assert all(e.source.startswith("pkg.core") and e.target.startswith("pkg.core") for e in graph.edges)


def test_build_dependency_graph_ignores_self_imports(tmp_path):
    # Not realistic Python, but guards the `target == mod` skip explicitly.
    _write(tmp_path, "pkg/__init__.py", "")
    _write(tmp_path, "pkg/a.py", "import pkg.a\n")

    graph = build_dependency_graph(tmp_path, _rules(tmp_path))
    assert graph.edges == []


def test_to_mermaid_and_to_dot_render_edges(tmp_path):
    _write(tmp_path, "pkg/__init__.py", "")
    _write(tmp_path, "pkg/a.py", "import pkg.b\n")
    _write(tmp_path, "pkg/b.py", "x = 1\n")

    graph = build_dependency_graph(tmp_path, _rules(tmp_path))
    mermaid = graph.to_mermaid()
    assert mermaid.startswith("graph LR")
    assert "pkg_a" in mermaid and "pkg_b" in mermaid

    dot = graph.to_dot()
    assert dot.startswith("digraph")
    assert '"pkg.a" -> "pkg.b"' in dot


def test_build_dependency_graph_resolves_src_layout_absolute_import(tmp_path):
    _write(tmp_path, "src/pkg/__init__.py", "")
    _write(tmp_path, "src/pkg/a.py", "import pkg.b\n")
    _write(tmp_path, "src/pkg/b.py", "x = 1\n")

    graph = build_dependency_graph(tmp_path, _rules(tmp_path))
    assert "pkg.a" in graph.nodes and "pkg.b" in graph.nodes
    assert any(e.source == "pkg.a" and e.target == "pkg.b" for e in graph.edges)


def test_fan_in_counts_incoming_edges(tmp_path):
    _write(tmp_path, "pkg/__init__.py", "")
    _write(tmp_path, "pkg/a.py", "import pkg.c\n")
    _write(tmp_path, "pkg/b.py", "import pkg.c\n")
    _write(tmp_path, "pkg/c.py", "x = 1\n")

    graph = build_dependency_graph(tmp_path, _rules(tmp_path))
    assert graph.fan_in()["pkg.c"] == 2
    assert graph.fan_in()["pkg.a"] == 0