from __future__ import annotations

from devtools.core.collector import chunk_by_tokens, collect_files, render_json, render_markdown, render_text
from devtools.core.ignore_rules import IgnoreRules


def _rules(root):
    return IgnoreRules.build(root, base_ignored_dirs=["node_modules", "__pycache__"])


def test_collect_files_skips_binary(sample_repo):
    (sample_repo / "logo.png").write_bytes(bytes(range(256)) * 4)
    result = collect_files(sample_repo, _rules(sample_repo))
    rel_paths = {f.rel_path for f in result.files}
    assert "logo.png" not in rel_paths
    assert "logo.png" in result.skipped_binary


def test_collect_files_respects_max_size(sample_repo):
    big = sample_repo / "big.txt"
    big.write_text("x" * 1000)
    result = collect_files(sample_repo, _rules(sample_repo), max_size=100)
    rel_paths = {f.rel_path for f in result.files}
    assert "big.txt" not in rel_paths
    assert "big.txt" in result.skipped_too_large


def test_collect_files_language_filter(sample_repo):
    result = collect_files(sample_repo, _rules(sample_repo), languages=["python"])
    assert all(f.language == "python" for f in result.files)
    assert any(f.rel_path == "src/main.py" for f in result.files)


def test_render_markdown_contains_all_files_and_is_deterministic(sample_repo):
    result = collect_files(sample_repo, _rules(sample_repo), languages=["python"])
    md1 = render_markdown(result, "sample")
    md2 = render_markdown(result, "sample")
    assert md1 == md2  # deterministic given the same repo state (spec §9)
    assert "src/main.py" in md1
    assert "```python" in md1


def test_render_json_shape(sample_repo):
    result = collect_files(sample_repo, _rules(sample_repo), languages=["python"])
    payload = render_json(result)
    assert payload["file_count"] == len(result.files)
    assert all("content" in f for f in payload["files"])


def test_render_text_uses_path_separators(sample_repo):
    result = collect_files(sample_repo, _rules(sample_repo), languages=["python"])
    text = render_text(result)
    assert "----- src/main.py -----" in text


def test_chunk_by_tokens_never_splits_a_single_file(sample_repo):
    result = collect_files(sample_repo, _rules(sample_repo))
    chunks = chunk_by_tokens(result.files, chunk_size=1)
    seen = []
    for chunk in chunks:
        seen.extend(chunk)
    assert len(seen) == len(result.files)
    assert all(len(chunk) >= 1 for chunk in chunks)