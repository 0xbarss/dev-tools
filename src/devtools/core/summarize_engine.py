"""`devtools summarize --repo` — AI architecture overview via a map-reduce
pass over `collect`'s output (proposal §4, backlog #22).

Also backs the map-reduce half of "context compression" (backlog #30,
previously partial): `chunk_by_tokens` already existed in `collector.py`
for token-budget truncation, but nothing summarized the *overflow*
content instead of just dropping it. `map_reduce_summarize` below is that
missing piece, and both `summarize --repo` and `context --compress` share
it rather than each rolling their own chunking/reduction logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from devtools.core.collector import CollectedFile, chunk_by_tokens, collect_files
from devtools.core.ignore_rules import IgnoreRules
from devtools.core.llm_client import LLMClient

_MAP_SYSTEM_PROMPT = (
    "You are summarizing one chunk of a larger codebase for later synthesis into an "
    "architecture overview. For the files below, note: their apparent purpose, key "
    "classes/functions/exports, and how they seem to relate to each other. Be concise "
    "(a few sentences per file at most) — this is an intermediate summary, not the final answer."
)

_REDUCE_SYSTEM_PROMPT = (
    "You are a senior engineer drafting an ARCHITECTURE.md overview of a codebase from "
    "chunk-level summaries (the codebase was too large for one pass, so it was "
    "summarized in pieces first). Synthesize them into ONE coherent overview covering: "
    "(1) what the project does, (2) its major components/modules and how they relate, "
    "(3) key design patterns or conventions you can infer, (4) anything that looks "
    "notable or worth a newcomer's attention. Use Markdown headings. Don't just "
    "concatenate the chunk summaries — actually synthesize them."
)

# Chunk size in tokens for the "map" pass; keeps each chunk request comfortably
# inside typical model context windows regardless of provider.
_DEFAULT_CHUNK_SIZE = 12_000


@dataclass
class SummarizeReport:
    chunk_count: int
    file_count: int
    chunk_summaries: list[str] = field(default_factory=list)
    overview: str = ""


def map_reduce_summarize(
    files: list[CollectedFile],
    client: LLMClient,
    chunk_size: int = _DEFAULT_CHUNK_SIZE,
    map_system_prompt: str = _MAP_SYSTEM_PROMPT,
    reduce_system_prompt: str = _REDUCE_SYSTEM_PROMPT,
) -> tuple[list[str], str]:
    """Chunk `files` by token budget, summarize each chunk (map), then
    synthesize the chunk summaries into one final pass (reduce). Returns
    (chunk_summaries, final_text). A single chunk skips the reduce call
    entirely — one chunk's summary already *is* the final answer."""
    if not files:
        return [], "No files to summarize (nothing matched, or everything was filtered out)."

    chunks = chunk_by_tokens(files, chunk_size)
    chunk_summaries: list[str] = []
    for i, chunk in enumerate(chunks, start=1):
        blocks = [f"## `{f.rel_path}`\n\n```{f.language if f.language != 'other' else ''}\n{f.content}\n```" for f in chunk]
        prompt = f"Chunk {i}/{len(chunks)} ({len(chunk)} file(s)):\n\n" + "\n\n".join(blocks)
        chunk_summaries.append(client.complete(prompt, system=map_system_prompt))

    if len(chunk_summaries) == 1:
        return chunk_summaries, chunk_summaries[0]

    reduce_prompt = "\n\n".join(f"### Chunk {i+1} summary\n\n{s}" for i, s in enumerate(chunk_summaries))
    final_text = client.complete(reduce_prompt, system=reduce_system_prompt)
    return chunk_summaries, final_text


def summarize_repo(
    root: Path,
    ignore_rules: IgnoreRules,
    client: LLMClient,
    languages: list[str] | None = None,
    chunk_size: int = _DEFAULT_CHUNK_SIZE,
    max_size: int | None = 200_000,
) -> SummarizeReport:
    result = collect_files(root, ignore_rules, languages=languages, max_size=max_size)
    chunk_summaries, overview = map_reduce_summarize(result.files, client, chunk_size=chunk_size)
    return SummarizeReport(chunk_count=len(chunk_summaries), file_count=len(result.files), chunk_summaries=chunk_summaries, overview=overview)


def render_markdown(report: SummarizeReport, project_name: str) -> str:
    lines = [f"# {project_name} — Architecture Overview", "", f"_Synthesized from {report.file_count} file(s) across {report.chunk_count} chunk(s)._", ""]
    lines.append(report.overview)
    return "\n".join(lines)
