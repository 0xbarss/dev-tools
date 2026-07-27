"""Builds an in-memory tree structure honoring ignore rules, depth, and the
--source-only filter, which each renderer (Rich / markdown / JSON) walks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from devtools.core.ignore_rules import IgnoreRules
from devtools.core.scanner import detect_language

NON_SOURCE_LANGUAGES = {"other"}


@dataclass
class TreeNode:
    name: str
    is_dir: bool
    children: list["TreeNode"] = field(default_factory=list)


def build_tree(
    root: Path,
    ignore_rules: IgnoreRules,
    max_depth: int | None = None,
    source_only: bool = False,
) -> TreeNode:
    def _build(path: Path, depth: int) -> TreeNode | None:
        is_dir = path.is_dir()
        if not is_dir and source_only and detect_language(path) in NON_SOURCE_LANGUAGES:
            return None
        node = TreeNode(name=path.name or str(path), is_dir=is_dir)
        if is_dir and (max_depth is None or depth < max_depth):
            try:
                children_paths = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name))
            except OSError:
                children_paths = []
            for child in children_paths:
                if ignore_rules.is_ignored(child):
                    continue
                child_node = _build(child, depth + 1)
                if child_node is not None:
                    node.children.append(child_node)
        return node

    return _build(root, 0) or TreeNode(name=root.name, is_dir=True)


def render_lines(node: TreeNode, prefix: str = "", is_last: bool = True, is_root: bool = True) -> list[str]:
    lines = []
    if is_root:
        lines.append(f"{node.name}/")
        for i, child in enumerate(node.children):
            lines.extend(render_lines(child, "", i == len(node.children) - 1, is_root=False))
        return lines

    connector = "└── " if is_last else "├── "
    suffix = "/" if node.is_dir else ""
    lines.append(f"{prefix}{connector}{node.name}{suffix}")
    extension = "    " if is_last else "│   "
    for i, child in enumerate(node.children):
        lines.extend(render_lines(child, prefix + extension, i == len(node.children) - 1, is_root=False))
    return lines


def render_markdown(node: TreeNode) -> str:
    lines = ["```text"]
    lines.extend(render_lines(node))
    lines.append("```")
    return "\n".join(lines)


def to_dict(node: TreeNode) -> dict:
    return {
        "name": node.name,
        "type": "dir" if node.is_dir else "file",
        "children": [to_dict(c) for c in node.children] if node.is_dir else [],
    }