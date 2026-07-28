from __future__ import annotations

from devtools.core.export_engine import cache_output, load_cached_output, to_csv, to_html_table, tree_to_html


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
