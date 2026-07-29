from __future__ import annotations

import time

import pytest

from devtools.core import index_engine
from devtools.core.ignore_rules import IgnoreRules


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setenv("DEVTOOLS_INDEX_DIR", str(tmp_path / "_index"))
    root = tmp_path / "proj"
    root.mkdir()
    (root / "a.py").write_text("def foo():\n    return 1\n")
    (root / "b.py").write_text("def bar():\n    return 2\n")
    rules = IgnoreRules.build(root, base_ignored_dirs=["node_modules", "__pycache__"])
    return root, rules


def test_build_indexes_all_files(project):
    root, rules = project
    count = index_engine.build(root, "proj1", rules)
    assert count == 2
    stats = index_engine.get_stats("proj1")
    assert stats.file_count == 2
    assert stats.has_vectors is False


def test_build_with_vectors(project):
    root, rules = project
    index_engine.build(root, "proj_vec", rules, with_vectors=True)
    stats = index_engine.get_stats("proj_vec")
    assert stats.has_vectors is True
    vectors = index_engine.load_vectors("proj_vec")
    assert set(vectors) == {"a.py", "b.py"}


def test_incremental_rebuild_skips_unchanged_files(project):
    root, rules = project
    index_engine.build(root, "proj_incr", rules)
    # Touch only one file with a later mtime.
    time.sleep(0.01)
    (root / "a.py").write_text("def foo():\n    return 42\n")
    import os

    os.utime(root / "a.py", None)
    changed = index_engine.build(root, "proj_incr", rules, incremental=True)
    assert changed == 1


def test_full_rebuild_rewrites_everything(project):
    root, rules = project
    index_engine.build(root, "proj_full", rules)
    changed = index_engine.build(root, "proj_full", rules, incremental=False)
    assert changed == 2


def test_is_fresh_true_after_build_false_after_change(project):
    root, rules = project
    index_engine.build(root, "proj_fresh", rules)
    assert index_engine.is_fresh(root, "proj_fresh", rules) is True
    time.sleep(0.01)
    (root / "c.py").write_text("def baz(): pass\n")
    assert index_engine.is_fresh(root, "proj_fresh", rules) is False


def test_stale_file_removed_from_index(project):
    root, rules = project
    index_engine.build(root, "proj_stale", rules)
    (root / "b.py").unlink()
    index_engine.build(root, "proj_stale", rules)
    stats = index_engine.get_stats("proj_stale")
    assert stats.file_count == 1


def test_cosine_similarity_identical_vectors_is_one():
    v = {"foo": 1.0, "bar": 2.0}
    assert index_engine.cosine_similarity(v, v) == pytest.approx(1.0)


def test_cosine_similarity_disjoint_vectors_is_zero():
    a = {"foo": 1.0}
    b = {"bar": 1.0}
    assert index_engine.cosine_similarity(a, b) == 0.0


def test_delete_index(project):
    root, rules = project
    index_engine.build(root, "proj_del", rules)
    assert index_engine.delete_index("proj_del") is True
    assert index_engine.delete_index("proj_del") is False