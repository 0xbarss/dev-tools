"""`devtools explain <file|function>` (proposal backlog #21, P0).

One-shot natural-language explanation using `context`'s existing internals
(search_engine + collector) to gather the relevant code, then a single
llm_client.complete() call to explain it. Deliberately thin: all the
interesting retrieval logic already exists elsewhere in the toolkit.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from devtools.core.collector import collect_files
from devtools.core.filesystem import read_text_safely
from devtools.core.ignore_rules import IgnoreRules
from devtools.core.llm_client import LLMClient
from devtools.core.search_engine import search as search_engine

_SYSTEM_PROMPT = (
    "You are a senior engineer explaining unfamiliar code to a teammate. "
    "Be concise, concrete, and reference specific functions/files by name. "
    "Structure your answer as: (1) what it does, (2) how it fits into the "
    "surrounding code, (3) anything surprising or worth double-checking."
)

_MAX_CONTEXT_FILES = 5
_MAX_FILE_BYTES = 40_000


@dataclass
class ExplainContext:
    target: str
    resolved_kind: str  # "file" | "symbol"
    file_paths: list[str]
    source_text: str


def build_context(root: Path, rules: IgnoreRules, target: str) -> ExplainContext:
    """Resolve `target` to either a direct file (if it exists on disk) or a
    symbol/concept, searched for via the same relevance search `context` uses."""
    candidate = (root / target).resolve()
    try:
        candidate.relative_to(root.resolve())
        is_within_root = True
    except ValueError:
        is_within_root = False

    if is_within_root and candidate.is_file():
        text = read_text_safely(candidate, max_bytes=_MAX_FILE_BYTES)
        if text is None:
            raise ValueError(f"'{target}' looks binary or unreadable — nothing to explain.")
        rel = candidate.relative_to(root.resolve()).as_posix()
        return ExplainContext(
            target=target,
            resolved_kind="file",
            file_paths=[rel],
            source_text=f"## `{rel}`\n\n```\n{text}\n```\n",
        )

    hits = search_engine(root, rules, target)[:_MAX_CONTEXT_FILES]
    if not hits:
        raise ValueError(
            f"Could not find a file at '{target}', and no matches for it as a symbol/concept either."
        )
    paths = [root / h.rel_path for h in hits]
    result = collect_files(root, rules, only_paths=paths, max_size=_MAX_FILE_BYTES)
    blocks = []
    for f in result.files:
        blocks.append(f"## `{f.rel_path}`\n\n```{f.language if f.language != 'other' else ''}\n{f.content}\n```\n")
    return ExplainContext(
        target=target,
        resolved_kind="symbol",
        file_paths=[f.rel_path for f in result.files],
        source_text="\n".join(blocks),
    )


def explain(root: Path, rules: IgnoreRules, target: str, client: LLMClient) -> str:
    ctx = build_context(root, rules, target)
    prompt = (
        f"Explain the following code, which is the result of searching a repository for "
        f"'{target}' (resolved as a {ctx.resolved_kind}).\n\n{ctx.source_text}"
    )
    return client.complete(prompt, system=_SYSTEM_PROMPT)