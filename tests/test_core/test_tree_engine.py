from __future__ import annotations

from devtools.core.ignore_rules import IgnoreRules
from devtools.core.tree_engine import build_tree, render_lines, to_dict


def _rules(root):
    return IgnoreRules.build(root, base_ignored_dirs=["node_modules", "__pycache__"])


def test_build_tree_excludes_ignored_dirs(sample_repo):
    node = build_tree(sample_repo, _rules(sample_repo))
    names = {c.name for c in node.children}
    assert "node_modules" not in names
    assert "src" in names


def test_max_depth_limits_descent(sample_repo):
    node = build_tree(sample_repo, _rules(sample_repo), max_depth=0)
    assert node.children == []


def test_source_only_hides_non_code_files(sample_repo):
    node = build_tree(sample_repo, _rules(sample_repo), source_only=True)
    rendered = "\n".join(render_lines(node))
    assert "README.md" not in rendered
    assert "main.py" in rendered


def test_to_dict_roundtrip_shape(sample_repo):
    node = build_tree(sample_repo, _rules(sample_repo), max_depth=1)
    d = to_dict(node)
    assert d["type"] == "dir"
    assert isinstance(d["children"], list)
