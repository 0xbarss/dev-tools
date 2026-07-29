from __future__ import annotations

from devtools.core.complexity_engine import compute_complexity, compute_file_complexity
from devtools.core.ignore_rules import IgnoreRules


def _rules(root):
    return IgnoreRules.build(root, base_ignored_dirs=["node_modules", "__pycache__"])


def test_simple_function_has_complexity_one(tmp_path):
    f = tmp_path / "mod.py"
    f.write_text("def add(a, b):\n    return a + b\n")
    result = compute_file_complexity(f, "mod.py")
    assert result is not None
    assert len(result.functions) == 1
    assert result.functions[0].complexity == 1
    assert result.functions[0].name == "add"


def test_branches_increase_complexity(tmp_path):
    f = tmp_path / "mod.py"
    f.write_text(
        "def classify(n):\n"
        "    if n < 0:\n"
        "        return 'neg'\n"
        "    elif n == 0:\n"
        "        return 'zero'\n"
        "    for i in range(n):\n"
        "        if i % 2 == 0:\n"
        "            pass\n"
        "    return 'pos'\n"
    )
    result = compute_file_complexity(f, "mod.py")
    assert result is not None
    fn = result.functions[0]
    # base(1) + if + elif + for + nested-if = 5
    assert fn.complexity == 5


def test_boolop_adds_a_branch_per_extra_operand(tmp_path):
    f = tmp_path / "mod.py"
    f.write_text("def check(a, b, c):\n    if a and b and c:\n        return True\n    return False\n")
    result = compute_file_complexity(f, "mod.py")
    fn = result.functions[0]
    # base(1) + if(1) + boolop with 3 operands (2) = 4
    assert fn.complexity == 4


def test_nested_function_scored_independently(tmp_path):
    f = tmp_path / "mod.py"
    f.write_text(
        "def outer(items):\n"
        "    def inner(x):\n"
        "        if x:\n"
        "            return 1\n"
        "        return 0\n"
        "    return [inner(i) for i in items]\n"
    )
    result = compute_file_complexity(f, "mod.py")
    by_name = {fn.qualname: fn for fn in result.functions}
    assert by_name["outer"].complexity == 2  # base + the comprehension's `for`
    assert by_name["outer.inner"].complexity == 2  # base + its own `if`, scored independently


def test_class_methods_are_included_with_qualname(tmp_path):
    f = tmp_path / "mod.py"
    f.write_text(
        "class Widget:\n"
        "    def render(self):\n"
        "        if self.visible:\n"
        "            return 'shown'\n"
        "        return 'hidden'\n"
    )
    result = compute_file_complexity(f, "mod.py")
    assert result.functions[0].qualname == "Widget.render"
    assert result.functions[0].complexity == 2


def test_binary_or_unreadable_file_returns_none(tmp_path):
    f = tmp_path / "data.bin"
    f.write_bytes(b"\x00\x01\x02\x03" * 100)
    assert compute_file_complexity(f, "data.bin") is None


def test_syntax_error_returns_none(tmp_path):
    f = tmp_path / "broken.py"
    f.write_text("def broken(:\n    pass\n")
    assert compute_file_complexity(f, "broken.py") is None


def test_compute_complexity_skips_files_with_no_functions(sample_repo):
    # sample_repo's pyproject.toml/README have no python functions at all.
    files = compute_complexity(sample_repo, _rules(sample_repo))
    rel_paths = {f.rel_path for f in files}
    assert "src/main.py" in rel_paths
    assert "src/auth.py" in rel_paths
    assert "pyproject.toml" not in rel_paths


def test_compute_complexity_ignores_non_python(sample_repo):
    files = compute_complexity(sample_repo, _rules(sample_repo))
    for f in files:
        assert f.rel_path.endswith(".py")