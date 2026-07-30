from __future__ import annotations

from devtools.core.deadcode_engine import (
    compute_deadcode,
    find_module_level_definitions,
    find_unused_imports,
)
from devtools.core.ignore_rules import IgnoreRules


def _rules(root):
    return IgnoreRules.build(root, base_ignored_dirs=["node_modules", "__pycache__"])


def test_find_unused_imports_flags_never_referenced_name(tmp_path):
    f = tmp_path / "mod.py"
    f.write_text("import os\nimport sys\n\ndef run():\n    return sys.argv\n")
    unused = find_unused_imports(f, "mod.py")
    assert [u.name for u in unused] == ["os"]


def test_find_unused_imports_respects_aliases(tmp_path):
    f = tmp_path / "mod.py"
    f.write_text("import numpy as np\n\ndef total(x):\n    return np.sum(x)\n")
    unused = find_unused_imports(f, "mod.py")
    assert unused == []


def test_find_unused_imports_respects_all_exports(tmp_path):
    f = tmp_path / "mod.py"
    f.write_text("from .helpers import util\n\n__all__ = ['util']\n")
    unused = find_unused_imports(f, "mod.py")
    assert unused == []


def test_find_unused_imports_ignores_future_annotations(tmp_path):
    f = tmp_path / "mod.py"
    f.write_text("from __future__ import annotations\n\nx = 1\n")
    unused = find_unused_imports(f, "mod.py")
    assert unused == []


def test_find_unused_imports_ignores_star_imports(tmp_path):
    f = tmp_path / "mod.py"
    f.write_text("from os import *\n")
    unused = find_unused_imports(f, "mod.py")
    assert unused == []


def test_find_module_level_definitions_excludes_dunders_and_tests(tmp_path):
    f = tmp_path / "mod.py"
    f.write_text(
        "def __init__(self):\n    pass\n\n"
        "def test_something():\n    assert True\n\n"
        "def helper():\n    return 1\n"
    )
    defs = find_module_level_definitions(f, "mod.py")
    names = {d.name for d in defs}
    assert names == {"helper"}


def test_find_module_level_definitions_include_tests_flag(tmp_path):
    f = tmp_path / "mod.py"
    f.write_text("def test_something():\n    assert True\n")
    defs = find_module_level_definitions(f, "mod.py", include_tests=True)
    assert {d.name for d in defs} == {"test_something"}


def test_find_module_level_definitions_excludes_decorated_by_default(tmp_path):
    f = tmp_path / "mod.py"
    f.write_text("import functools\n\n@functools.cache\ndef compute():\n    return 1\n")
    defs = find_module_level_definitions(f, "mod.py")
    assert defs == []
    defs_included = find_module_level_definitions(f, "mod.py", include_decorated=True)
    assert {d.name for d in defs_included} == {"compute"}


def test_find_module_level_definitions_skips_nested_functions(tmp_path):
    f = tmp_path / "mod.py"
    f.write_text("def outer():\n    def inner():\n        return 1\n    return inner()\n")
    defs = find_module_level_definitions(f, "mod.py")
    assert {d.name for d in defs} == {"outer"}


def test_compute_deadcode_flags_never_called_function(tmp_path):
    (tmp_path / "used.py").write_text("def helper():\n    return 1\n\ndef never_called():\n    return 2\n\nprint(helper())\n")
    report = compute_deadcode(tmp_path, _rules(tmp_path))
    unused_names = {d.name for d in report.unused_definitions}
    assert "never_called" in unused_names
    assert "helper" not in unused_names


def test_compute_deadcode_finds_cross_file_usage(tmp_path):
    (tmp_path / "lib.py").write_text("def shared():\n    return 42\n")
    (tmp_path / "main.py").write_text("from lib import shared\n\nprint(shared())\n")
    report = compute_deadcode(tmp_path, _rules(tmp_path))
    unused_names = {d.name for d in report.unused_definitions}
    assert "shared" not in unused_names


def test_compute_deadcode_empty_project_has_no_findings(tmp_path):
    (tmp_path / "empty.py").write_text("x = 1\n")
    report = compute_deadcode(tmp_path, _rules(tmp_path))
    assert report.total == 0


def test_compute_deadcode_on_sample_repo_finds_entrypoint_never_called(sample_repo):
    # sample_repo's auth.py chain: authenticate/check_credential are called
    # from within login, but nothing in the fixture repo ever calls login
    # itself (test_auth.py's test_login doesn't call it) — so login is the
    # one genuinely unused definition. main.py's `main` is called under
    # `__main__`, so it isn't flagged.
    report = compute_deadcode(sample_repo, _rules(sample_repo))
    unused_names = {d.name for d in report.unused_definitions}
    assert unused_names == {"login"}
