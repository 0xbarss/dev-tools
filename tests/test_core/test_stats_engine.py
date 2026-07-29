from __future__ import annotations

from devtools.core.ignore_rules import IgnoreRules
from devtools.core.stats_engine import compute_stats, find_duplicate_files


def _rules(root):
    return IgnoreRules.build(root, base_ignored_dirs=["node_modules", "__pycache__"])


def test_compute_stats_counts_files_and_lines(sample_repo):
    stats = compute_stats(sample_repo, _rules(sample_repo))
    assert stats.file_count > 0
    assert stats.total_lines > 0
    assert "python" in stats.language_counts


def test_compute_stats_largest_files_sorted_desc(sample_repo):
    stats = compute_stats(sample_repo, _rules(sample_repo), top=3)
    sizes = [f.size for f in stats.largest_files]
    assert sizes == sorted(sizes, reverse=True)
    assert len(stats.largest_files) <= 3


def test_find_duplicate_files(sample_repo):
    (sample_repo / "src" / "copy_of_main.py").write_text((sample_repo / "src" / "main.py").read_text())
    dups = find_duplicate_files(sample_repo, _rules(sample_repo))
    all_dup_paths = [p for paths in dups.values() for p in paths]
    assert "src/main.py" in all_dup_paths
    assert "src/copy_of_main.py" in all_dup_paths


def test_no_duplicates_when_files_differ(sample_repo):
    dups = find_duplicate_files(sample_repo, _rules(sample_repo))
    assert dups == {}