from __future__ import annotations

import pytest

from devtools.utils.helpers import ParseError, human_size, parse_duration_to_seconds, parse_size, slugify


@pytest.mark.parametrize(
    "text,expected",
    [
        ("5MB", 5 * 1024 * 1024),
        ("512K", 512 * 1024),
        ("10", 10),
        ("1.5GB", int(1.5 * 1024**3)),
    ],
)
def test_parse_size(text, expected):
    assert parse_size(text) == expected


def test_parse_size_invalid_raises():
    with pytest.raises(ParseError):
        parse_size("not-a-size")


@pytest.mark.parametrize(
    "text,expected_seconds",
    [
        ("30d", 30 * 86400),
        ("2w", 2 * 604800),
        ("12h", 12 * 3600),
        ("5m", 5 * 60),
    ],
)
def test_parse_duration(text, expected_seconds):
    assert parse_duration_to_seconds(text) == expected_seconds


def test_parse_duration_invalid_raises():
    with pytest.raises(ParseError):
        parse_duration_to_seconds("thirty days")


def test_human_size_formats_reasonably():
    assert human_size(500) == "500B"
    assert "KB" in human_size(2048)
    assert "MB" in human_size(5 * 1024 * 1024)


def test_slugify():
    assert slugify("My Cool Project!") == "my-cool-project"