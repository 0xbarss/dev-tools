from __future__ import annotations

from devtools.core.ignore_rules import IgnoreRules
from devtools.core.scanner import detect_language, normalize_lang, scan_project


def test_detect_language_by_extension(sample_repo):
    assert detect_language(sample_repo / "src" / "main.py") == "python"
    assert detect_language(sample_repo / "README.md") == "markdown"
    assert detect_language(sample_repo / "pyproject.toml") == "toml"


def test_detect_language_unknown_extension_is_other(tmp_path):
    f = tmp_path / "data.xyz123"
    f.write_text("?")
    assert detect_language(f) == "other"


def test_normalize_lang_aliases():
    assert normalize_lang("PY") == "python"
    assert normalize_lang("JS") == "javascript"
    assert normalize_lang("python") == "python"


def test_scan_project_filters_by_language(sample_repo):
    rules = IgnoreRules.build(sample_repo, base_ignored_dirs=["node_modules", "__pycache__"])
    py_files = {e.rel_path for e in scan_project(sample_repo, rules, languages=["python"])}
    assert "src/main.py" in py_files
    assert "README.md" not in py_files


def test_scan_project_respects_ignore_rules(sample_repo):
    rules = IgnoreRules.build(sample_repo, base_ignored_dirs=["node_modules", "__pycache__"])
    all_files = {e.rel_path for e in scan_project(sample_repo, rules)}
    assert not any(f.startswith("node_modules/") for f in all_files)