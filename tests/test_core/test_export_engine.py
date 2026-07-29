from __future__ import annotations

import json

from devtools.core.export_engine import cache_output, load_cached_output, to_csv, to_html_table, to_sarif, tree_to_html


def test_cache_and_load_roundtrip():
    cache_output("stats", "demo", {"files": [{"name": "a.py", "lines": 10}]})
    data = load_cached_output("stats", "demo")
    assert data == {"files": [{"name": "a.py", "lines": 10}]}


def test_load_cached_output_missing_returns_none():
    assert load_cached_output("nope", "demo-missing-project") is None


def test_to_csv_produces_header_and_rows():
    rows = [{"name": "a.py", "lines": 10}, {"name": "b.py", "lines": 20}]
    csv_text = to_csv(rows)
    lines = csv_text.strip().splitlines()
    assert lines[0] == "name,lines"
    assert "a.py,10" in lines[1]


def test_to_csv_empty_rows_returns_empty_string():
    assert to_csv([]) == ""


def test_to_html_table_escapes_and_includes_rows():
    rows = [{"name": "<script>", "lines": 1}]
    html_text = to_html_table("Title", rows)
    assert "<table>" in html_text
    assert "&lt;script&gt;" in html_text


def test_tree_to_html_renders_nested_structure():
    tree = {"name": "root", "type": "dir", "children": [{"name": "a.py", "type": "file"}]}
    html_text = tree_to_html("tree", tree)
    assert "a.py" in html_text
    assert "<ul>" in html_text


def test_to_sarif_produces_valid_shape_with_one_result_per_finding():
    findings = [
        {"file": "src/a.py", "line": 10, "rule": "E501", "severity": "error", "message": "line too long", "source_linter": "ruff"},
        {"file": "src/b.py", "line": 3, "rule": "F401", "severity": "warning", "message": "unused import", "source_linter": "ruff"},
    ]
    sarif_text = to_sarif(findings)
    doc = json.loads(sarif_text)

    assert doc["version"] == "2.1.0"
    assert len(doc["runs"]) == 1
    results = doc["runs"][0]["results"]
    assert len(results) == 2
    assert results[0]["ruleId"] == "E501"
    assert results[0]["level"] == "error"
    assert results[0]["locations"][0]["physicalLocation"]["artifactLocation"]["uri"] == "src/a.py"
    assert results[0]["locations"][0]["physicalLocation"]["region"]["startLine"] == 10
    assert results[1]["level"] == "warning"


def test_to_sarif_deduplicates_rule_ids_in_driver_rules():
    findings = [
        {"file": "a.py", "line": 1, "rule": "E501", "severity": "error", "message": "x", "source_linter": "ruff"},
        {"file": "b.py", "line": 2, "rule": "E501", "severity": "error", "message": "y", "source_linter": "ruff"},
    ]
    doc = json.loads(to_sarif(findings))
    rule_ids = [r["id"] for r in doc["runs"][0]["tool"]["driver"]["rules"]]
    assert rule_ids == ["E501"]


def test_to_sarif_handles_missing_line_and_rule_gracefully():
    findings = [{"file": "a.py", "line": None, "rule": None, "severity": "info", "message": "note", "source_linter": "mypy"}]
    doc = json.loads(to_sarif(findings))
    result = doc["runs"][0]["results"][0]
    assert result["ruleId"] == "unspecified"
    assert result["level"] == "note"
    assert result["locations"][0]["physicalLocation"]["region"]["startLine"] == 1


def test_to_sarif_empty_findings_produces_empty_results():
    doc = json.loads(to_sarif([]))
    assert doc["runs"][0]["results"] == []
