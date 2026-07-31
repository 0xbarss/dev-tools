from __future__ import annotations

import json

import pytest

from devtools.core.collector import collect_files, render_json, render_markdown, render_text
from devtools.core.expand_engine import (
    ExpandParseError,
    UnsafePathError,
    detect_format,
    expand,
    parse_json,
    parse_markdown,
    parse_text,
)
from devtools.core.ignore_rules import IgnoreRules


def _rules(root):
    return IgnoreRules.build(root, base_ignored_dirs=["node_modules", "__pycache__"])


def _collect(root):
    return collect_files(root, _rules(root))


# --------------------------------------------------------------------------- #
# Round-trip parsing against the real collector.render_* output
# --------------------------------------------------------------------------- #


def test_markdown_round_trip(sample_repo):
    result = _collect(sample_repo)
    rendered = render_markdown(result, "sample_repo")
    parsed = {f.rel_path: f.content for f in parse_markdown(rendered)}
    original = {f.rel_path: f.content for f in result.files}
    for rel_path, content in original.items():
        # render_markdown intentionally rstrips trailing newlines per file --
        # that's the one inherent, documented lossy edge of the markdown
        # format itself, not a parsing bug.
        assert parsed[rel_path] == content.rstrip("\n")


def test_json_round_trip_is_lossless(sample_repo):
    result = _collect(sample_repo)
    rendered = json.dumps(render_json(result))
    parsed = {f.rel_path: f.content for f in parse_json(rendered)}
    original = {f.rel_path: f.content for f in result.files}
    assert parsed == original  # json preserves content exactly, incl. trailing newlines


def test_text_round_trip(sample_repo):
    result = _collect(sample_repo)
    rendered = render_text(result)
    parsed = {f.rel_path: f.content for f in parse_text(rendered)}
    original = {f.rel_path: f.content for f in result.files}
    for rel_path, content in original.items():
        assert parsed[rel_path].rstrip("\n") == content.rstrip("\n")


def test_markdown_parser_handles_nested_backtick_fences():
    # A collected file whose *own* content contains a bare ``` line (e.g. a
    # README with a code sample) -- the exact case a naive "read until the
    # first closing fence" parser breaks on.
    content = (
        "# demo\n\n"
        "## `docs/guide.md`\n\n"
        "```markdown\n"
        "# Guide\n\n"
        "```python\n"
        'print("hi")\n'
        "```\n\n"
        "More text after.\n"
        "```\n\n"
        "## `src/main.py`\n\n"
        "```python\n"
        "def main(): pass\n"
        "```\n"
    )
    files = {f.rel_path: f.content for f in parse_markdown(content)}
    assert files["src/main.py"] == "def main(): pass"
    assert "```python\nprint(\"hi\")\n```" in files["docs/guide.md"]
    assert files["docs/guide.md"].endswith("More text after.")


def test_markdown_parser_drops_trailing_skipped_sections():
    content = (
        "# demo\n\n"
        "## `src/main.py`\n\n"
        "```python\n"
        "x = 1\n"
        "```\n\n"
        "## Skipped (binary)\n"
        "- logo.png\n\n"
        "## Skipped (too large)\n"
        "- big.bin\n"
    )
    files = parse_markdown(content)
    assert len(files) == 1
    assert files[0].rel_path == "src/main.py"
    assert files[0].content == "x = 1"


# --------------------------------------------------------------------------- #
# Format auto-detection
# --------------------------------------------------------------------------- #


def test_detect_format_by_extension(tmp_path):
    assert detect_format(tmp_path / "x.md", "") == "markdown"
    assert detect_format(tmp_path / "x.json", "") == "json"
    assert detect_format(tmp_path / "x.txt", "") == "text"


def test_detect_format_by_content_sniffing(tmp_path):
    assert detect_format(tmp_path / "x.dump", '{"files": []}') == "json"
    assert detect_format(tmp_path / "x.dump", "## `a.py`\n\n```python\nx\n```\n") == "markdown"
    assert detect_format(tmp_path / "x.dump", "----- a.py -----\nx\n") == "text"


# --------------------------------------------------------------------------- #
# Malformed input
# --------------------------------------------------------------------------- #


def test_parse_markdown_rejects_content_with_no_headers():
    with pytest.raises(ExpandParseError):
        parse_markdown("just some prose, no file blocks here")


def test_parse_json_rejects_non_collect_shape():
    with pytest.raises(ExpandParseError):
        parse_json('{"not": "the right shape"}')


def test_parse_json_rejects_invalid_json():
    with pytest.raises(ExpandParseError):
        parse_json("{not json")


# --------------------------------------------------------------------------- #
# expand() -- the file-writing half
# --------------------------------------------------------------------------- #


def test_expand_writes_files_and_creates_directories(tmp_path):
    source = tmp_path / "dump.md"
    source.write_text(
        "# demo\n\n## `src/nested/main.py`\n\n```python\nprint('hi')\n```\n",
        encoding="utf-8",
    )
    target = tmp_path / "out"
    result = expand(source, target)
    assert result.written == ["src/nested/main.py"]
    assert (target / "src" / "nested" / "main.py").read_text() == "print('hi')"


def test_expand_refuses_path_traversal(tmp_path):
    source = tmp_path / "dump.md"
    source.write_text(
        "# demo\n\n## `../../etc/passwd`\n\n```text\npwned\n```\n",
        encoding="utf-8",
    )
    with pytest.raises(UnsafePathError):
        expand(source, tmp_path / "out")


def test_expand_refuses_absolute_path_traversal(tmp_path):
    source = tmp_path / "dump.md"
    source.write_text(
        "# demo\n\n## `/etc/passwd`\n\n```text\npwned\n```\n",
        encoding="utf-8",
    )
    with pytest.raises(UnsafePathError):
        expand(source, tmp_path / "out")


def test_expand_detects_conflicts_without_force(tmp_path):
    target = tmp_path / "out"
    (target / "src").mkdir(parents=True)
    (target / "src" / "main.py").write_text("original content\n")

    source = tmp_path / "dump.md"
    source.write_text(
        "# demo\n\n## `src/main.py`\n\n```python\nnew content\n```\n",
        encoding="utf-8",
    )
    with pytest.raises(FileExistsError):
        expand(source, target)
    # untouched
    assert (target / "src" / "main.py").read_text() == "original content\n"


def test_expand_force_overwrites_conflicts(tmp_path):
    target = tmp_path / "out"
    (target / "src").mkdir(parents=True)
    (target / "src" / "main.py").write_text("original content\n")

    source = tmp_path / "dump.md"
    source.write_text(
        "# demo\n\n## `src/main.py`\n\n```python\nnew content\n```\n",
        encoding="utf-8",
    )
    result = expand(source, target, force=True)
    assert result.written == ["src/main.py"]
    assert (target / "src" / "main.py").read_text() == "new content"


def test_expand_skips_files_already_identical(tmp_path):
    target = tmp_path / "out"
    (target / "src").mkdir(parents=True)
    (target / "src" / "main.py").write_text("same content")

    source = tmp_path / "dump.md"
    source.write_text(
        "# demo\n\n## `src/main.py`\n\n```python\nsame content\n```\n",
        encoding="utf-8",
    )
    result = expand(source, target)
    assert result.written == []
    assert result.skipped_existing == ["src/main.py"]


def test_expand_auto_detects_json_format(tmp_path):
    source = tmp_path / "dump.json"
    source.write_text(json.dumps({"files": [{"path": "a.py", "content": "x = 1"}]}), encoding="utf-8")
    result = expand(source, tmp_path / "out")
    assert result.written == ["a.py"]
    assert (tmp_path / "out" / "a.py").read_text() == "x = 1"
