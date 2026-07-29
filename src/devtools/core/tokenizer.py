"""Token counting for collect/bundle/stats.

Per spec §2, tiktoken is preferred but a local approximation is an accepted
fallback — this keeps `devtools` usable on machines where tiktoken (a compiled
extension) isn't installed, without making it a hard runtime dependency.
"""

from __future__ import annotations

from functools import lru_cache

_ENCODING_NAME = "cl100k_base"


@lru_cache(maxsize=1)
def _get_encoder():
    try:
        import tiktoken

        return tiktoken.get_encoding(_ENCODING_NAME)
    except Exception:
        return None


def count_tokens(text: str) -> int:
    """Return an exact (tiktoken) or approximate token count for `text`."""
    if not text:
        return 0
    encoder = _get_encoder()
    if encoder is not None:
        return len(encoder.encode(text, disallowed_special=()))
    return approximate_token_count(text)


def approximate_token_count(text: str) -> int:
    """Local approximation used when tiktoken is unavailable.

    Roughly 1 token per 4 characters is the well-known GPT-family heuristic;
    we blend it with a whitespace-token count and take the average, which
    tracks real tokenizer output more closely across both prose and code.
    """
    if not text:
        return 0
    char_estimate = len(text) / 4
    word_estimate = len(text.split()) / 0.75
    return max(1, round((char_estimate + word_estimate) / 2))


def is_using_real_tokenizer() -> bool:
    return _get_encoder() is not None