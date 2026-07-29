from __future__ import annotations

from devtools.core.tokenizer import approximate_token_count, count_tokens


def test_empty_string_is_zero_tokens():
    assert count_tokens("") == 0


def test_count_tokens_returns_positive_for_nonempty_text():
    assert count_tokens("def hello():\n    print('hi')\n") > 0


def test_approximate_token_count_scales_with_length():
    short = approximate_token_count("hello world")
    long = approximate_token_count("hello world " * 50)
    assert long > short


def test_approximate_token_count_never_zero_for_nonempty_text():
    assert approximate_token_count("x") >= 1