from __future__ import annotations

from devtools.core.filesystem import file_hash, is_probably_binary, read_text_safely


def test_is_probably_binary_detects_null_bytes(tmp_path):
    f = tmp_path / "bin.dat"
    f.write_bytes(b"\x00\x01\x02text")
    assert is_probably_binary(f) is True


def test_is_probably_binary_false_for_text(tmp_path):
    f = tmp_path / "text.py"
    f.write_text("print('hello world')\n")
    assert is_probably_binary(f) is False


def test_read_text_safely_returns_none_for_binary(tmp_path):
    f = tmp_path / "bin.dat"
    f.write_bytes(bytes(range(256)) * 4)
    assert read_text_safely(f) is None


def test_read_text_safely_returns_none_over_max_bytes(tmp_path):
    f = tmp_path / "big.txt"
    f.write_text("x" * 1000)
    assert read_text_safely(f, max_bytes=10) is None


def test_read_text_safely_reads_normal_file(tmp_path):
    f = tmp_path / "ok.txt"
    f.write_text("hello")
    assert read_text_safely(f) == "hello"


def test_file_hash_matches_for_identical_content(tmp_path):
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_text("same content")
    b.write_text("same content")
    assert file_hash(a) == file_hash(b)


def test_file_hash_differs_for_different_content(tmp_path):
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_text("content one")
    b.write_text("content two")
    assert file_hash(a) != file_hash(b)
