from __future__ import annotations

from devtools.core.dupes_engine import find_code_duplicates
from devtools.core.ignore_rules import IgnoreRules


def _rules(root):
    return IgnoreRules.build(root, base_ignored_dirs=["node_modules", "__pycache__"])


_BLOCK = (
    "def process(items):\n"
    "    total = 0\n"
    "    for item in items:\n"
    "        total += item\n"
    "    return total\n"
)


def test_finds_exact_duplicate_block_across_files(tmp_path):
    # Windows are taken at a fixed min_lines stride (see module docstring),
    # so the block needs to start at a window boundary in both files to be
    # recognized as the same shingle — here, at the very top of each file.
    (tmp_path / "a.py").write_text(_BLOCK)
    (tmp_path / "b.py").write_text(_BLOCK)
    groups = find_code_duplicates(tmp_path, _rules(tmp_path), min_lines=5)
    assert len(groups) == 1
    paths = {o.rel_path for o in groups[0].occurrences}
    assert paths == {"a.py", "b.py"}


def test_misaligned_duplicate_across_files_is_missed_by_design(tmp_path):
    # Documents the known stride-alignment limitation: the same block,
    # shifted by an unrelated leading line in one file, no longer lands on
    # the same window boundary and so isn't matched.
    (tmp_path / "a.py").write_text(_BLOCK)
    (tmp_path / "b.py").write_text("# unrelated header\n" + _BLOCK)
    groups = find_code_duplicates(tmp_path, _rules(tmp_path), min_lines=5)
    assert groups == []


def test_no_duplicates_below_min_lines_across_unrelated_files(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\ny = 2\n")
    (tmp_path / "b.py").write_text("x = 1\ny = 2\n")
    # min_lines larger than either file's non-blank line count
    groups = find_code_duplicates(tmp_path, _rules(tmp_path), min_lines=6)
    assert groups == []


def test_whitespace_and_indentation_differences_still_match(tmp_path):
    (tmp_path / "a.py").write_text(_BLOCK)
    reindented = _BLOCK.replace("    ", "        ")  # double the indentation
    (tmp_path / "b.py").write_text(reindented)
    groups = find_code_duplicates(tmp_path, _rules(tmp_path), min_lines=5)
    assert len(groups) == 1


def test_distinct_code_has_no_duplicates(tmp_path):
    (tmp_path / "a.py").write_text("def add(a, b):\n    return a + b\n")
    (tmp_path / "b.py").write_text("def multiply(a, b):\n    return a * b\n")
    groups = find_code_duplicates(tmp_path, _rules(tmp_path), min_lines=2)
    assert groups == []


def test_language_filter_limits_scan(tmp_path):
    (tmp_path / "a.py").write_text(_BLOCK)
    (tmp_path / "b.js").write_text(_BLOCK)
    groups = find_code_duplicates(tmp_path, _rules(tmp_path), min_lines=5, languages=["python"])
    for g in groups:
        for o in g.occurrences:
            assert o.rel_path.endswith(".py")


def test_intra_file_duplicate_block_is_detected(tmp_path):
    (tmp_path / "a.py").write_text(_BLOCK + "\n\n" + _BLOCK)
    groups = find_code_duplicates(tmp_path, _rules(tmp_path), min_lines=5)
    assert len(groups) == 1
    assert len(groups[0].occurrences) == 2
    assert all(o.rel_path == "a.py" for o in groups[0].occurrences)


def test_groups_sorted_by_occurrence_count_descending(tmp_path):
    (tmp_path / "a.py").write_text(_BLOCK)
    (tmp_path / "b.py").write_text(_BLOCK)
    (tmp_path / "c.py").write_text(_BLOCK)
    other_block = "def other(x):\n    y = x\n    z = y\n    return z\nf = 1\n"
    (tmp_path / "d.py").write_text(other_block)
    (tmp_path / "e.py").write_text(other_block)
    groups = find_code_duplicates(tmp_path, _rules(tmp_path), min_lines=5)
    counts = [len(g.occurrences) for g in groups]
    assert counts == sorted(counts, reverse=True)