from __future__ import annotations

from devtools.core.health_engine import compute_health
from devtools.core.ignore_rules import IgnoreRules


def _rules(root):
    return IgnoreRules.build(root, base_ignored_dirs=["node_modules", "__pycache__"])


def test_compute_health_returns_four_categories_summing_to_100_weight(sample_repo):
    report = compute_health(sample_repo, _rules(sample_repo), ignored_dirs=["node_modules"])
    assert {c.name for c in report.categories} == {"doctor", "lint", "complexity", "duplication"}
    assert sum(c.weight for c in report.categories) == 100


def test_compute_health_overall_score_within_bounds(sample_repo):
    report = compute_health(sample_repo, _rules(sample_repo), ignored_dirs=["node_modules"])
    assert 0 <= report.overall_score <= 100
    for c in report.categories:
        assert 0 <= c.score <= c.weight


def test_compute_health_penalizes_duplicated_code(tmp_path):
    shared = "\n".join(f"line {i}" for i in range(60)) + "\n"
    (tmp_path / "a.py").write_text(shared)
    (tmp_path / "b.py").write_text(shared)
    rules = _rules(tmp_path)

    report = compute_health(tmp_path, rules, ignored_dirs=[])
    dup = next(c for c in report.categories if c.name == "duplication")
    assert dup.score < dup.weight


def test_compute_health_no_python_functions_gives_full_complexity_score(tmp_path):
    (tmp_path / "README.md").write_text("# hi\n")
    report = compute_health(tmp_path, _rules(tmp_path), ignored_dirs=[])
    complexity = next(c for c in report.categories if c.name == "complexity")
    assert complexity.score == complexity.weight