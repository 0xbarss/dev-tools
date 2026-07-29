"""`devtools investigate` — autonomous investigation mode (Prioritized
Backlog: "Autonomous investigation mode", P2).

A bounded ReAct-style loop on top of tools that already exist in this
codebase (`search_engine.search`, `filesystem.read_text_safely`) rather than
free-form code execution: at each step the model chooses one action —
`search`, `read`, or `finish` — from a fixed menu, this module executes it
against the project on disk, and feeds the (truncated) result back. This
keeps the "autonomous" part meaningfully bounded (`max_steps`, per-file byte
caps, project-root containment) instead of an open-ended agent loop, which
is the main risk the proposal itself calls out for this feature.

Degrades the same way `review_engine.py` does: if the model's response isn't
well-formed JSON for an action, the loop stops and whatever text came back is
surfaced directly as the summary rather than crashing.
"""

from __future__ import annotations

import json as _json
from dataclasses import dataclass, field
from pathlib import Path

from devtools.core.filesystem import read_text_safely
from devtools.core.ignore_rules import IgnoreRules
from devtools.core.llm_client import LLMClient
from devtools.core.search_engine import search as search_engine

_SYSTEM_PROMPT = (
    "You are investigating a codebase to answer a question or diagnose an issue. "
    "You have exactly two tools: `search` (keyword/concept search over the repo, "
    "returns matching file paths and sample lines) and `read` (read a specific "
    "file's contents, given its path relative to the repo root). Use them to "
    "gather evidence step by step; don't guess at code you haven't seen. "
    "Respond with ONLY a single JSON object, no prose outside it, each turn:\n"
    '  {"action": "search", "query": "<concept or keywords>"}\n'
    '  {"action": "read", "path": "<relative/path.ext>"}\n'
    '  {"action": "finish", "summary": "<findings, in plain language>", '
    '"evidence": ["<file path>", ...]}\n'
    "Call `finish` as soon as you have enough evidence to answer confidently, "
    "and always within the step budget you're given."
)

_MAX_STEPS_DEFAULT = 5
_MAX_FILE_BYTES = 20_000
_MAX_SEARCH_HITS = 8
_MAX_TRANSCRIPT_CHARS = 40_000


@dataclass
class InvestigationStep:
    action: str  # "search" | "read" | "finish" | "error"
    detail: str  # the query/path/summary
    observation: str = ""  # tool result fed back to the model


@dataclass
class InvestigationReport:
    question: str
    steps: list[InvestigationStep] = field(default_factory=list)
    summary: str = ""
    evidence: list[str] = field(default_factory=list)
    raw_text: str | None = None  # populated only if the model never produced valid JSON


def _extract_json_object(text: str) -> dict | None:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        return _json.loads(text)
    except _json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return _json.loads(text[start : end + 1])
            except _json.JSONDecodeError:
                return None
        return None


def _safe_resolve(root: Path, rel_path: str) -> Path | None:
    """Resolve rel_path against root, refusing anything that escapes it."""
    candidate = (root / rel_path).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        return None
    return candidate


def _run_search(root: Path, rules: IgnoreRules, query: str) -> str:
    hits = search_engine(root, rules, query)[:_MAX_SEARCH_HITS]
    if not hits:
        return f"No matches for '{query}'."
    lines = [f"Top matches for '{query}':"]
    for h in hits:
        samples = "; ".join(f"{m.rel_path}:{m.line_number}: {m.line.strip()[:120]}" for m in h.sample_matches[:2])
        lines.append(f"- {h.rel_path} (score {h.score}){': ' + samples if samples else ''}")
    return "\n".join(lines)


def _run_read(root: Path, rel_path: str) -> str:
    resolved = _safe_resolve(root, rel_path)
    if resolved is None:
        return f"Refused: '{rel_path}' is outside the project root."
    if not resolved.is_file():
        return f"No such file: '{rel_path}'."
    text = read_text_safely(resolved, max_bytes=_MAX_FILE_BYTES)
    if text is None:
        return f"'{rel_path}' looks binary or unreadable."
    return f"Contents of {rel_path}:\n```\n{text}\n```"


def investigate(
    root: Path,
    rules: IgnoreRules,
    client: LLMClient,
    question: str,
    max_steps: int = _MAX_STEPS_DEFAULT,
) -> InvestigationReport:
    if max_steps < 1:
        raise ValueError("max_steps must be at least 1.")

    transcript = [f"Question: {question}", f"You have a budget of {max_steps} step(s)."]
    steps: list[InvestigationStep] = []

    for step_index in range(max_steps):
        remaining = max_steps - step_index
        prompt = "\n\n".join(transcript) + f"\n\n({remaining} step(s) remaining, including this one.)"
        response = client.complete(prompt, system=_SYSTEM_PROMPT)
        parsed = _extract_json_object(response)

        if parsed is None or "action" not in parsed:
            return InvestigationReport(question=question, steps=steps, summary="(unstructured response — see raw_text)", raw_text=response)

        action = parsed.get("action")

        if action == "finish":
            summary = parsed.get("summary", "").strip()
            evidence = [e for e in parsed.get("evidence", []) if isinstance(e, str)]
            steps.append(InvestigationStep(action="finish", detail=summary))
            return InvestigationReport(question=question, steps=steps, summary=summary, evidence=evidence)

        if action == "search":
            query = str(parsed.get("query", "")).strip()
            observation = _run_search(root, rules, query) if query else "No query given; skipping this step."
        elif action == "read":
            path = str(parsed.get("path", "")).strip()
            observation = _run_read(root, path) if path else "No path given; skipping this step."
        else:
            observation = f"Unknown action '{action}'. Choose search, read, or finish."

        step = InvestigationStep(action=action, detail=parsed.get("query") or parsed.get("path") or "", observation=observation)
        steps.append(step)
        transcript.append(f"Step {step_index + 1} — {action}({step.detail}):\n{observation}")

        # Keep the running transcript bounded so long investigations don't
        # blow past the model's context window.
        joined = "\n\n".join(transcript)
        if len(joined) > _MAX_TRANSCRIPT_CHARS:
            transcript = [transcript[0], transcript[1], "(earlier steps omitted for length)", transcript[-1]]

    # Ran out of steps without an explicit `finish` — ask once more for a
    # forced wrap-up rather than returning nothing.
    wrap_prompt = "\n\n".join(transcript) + "\n\nYou're out of steps. Respond now with only the `finish` JSON action."
    response = client.complete(wrap_prompt, system=_SYSTEM_PROMPT)
    parsed = _extract_json_object(response)
    if parsed and parsed.get("action") == "finish":
        summary = parsed.get("summary", "").strip()
        evidence = [e for e in parsed.get("evidence", []) if isinstance(e, str)]
        steps.append(InvestigationStep(action="finish", detail=summary))
        return InvestigationReport(question=question, steps=steps, summary=summary, evidence=evidence)
    return InvestigationReport(
        question=question,
        steps=steps,
        summary="(step budget exhausted without a structured conclusion — see raw_text)",
        raw_text=response,
    )


def render_markdown(report: InvestigationReport, project_name: str) -> str:
    lines = [f"# Investigation — {project_name}", "", f"**Question:** {report.question}", ""]
    if report.raw_text:
        lines += ["## Raw model output", "", report.raw_text]
        return "\n".join(lines)
    lines += ["## Summary", "", report.summary, ""]
    if report.evidence:
        lines.append("## Evidence")
        lines.append("")
        lines.extend(f"- `{e}`" for e in report.evidence)
        lines.append("")
    if report.steps:
        lines.append("## Steps taken")
        lines.append("")
        for i, s in enumerate(report.steps, 1):
            lines.append(f"{i}. **{s.action}** `{s.detail}`")
    return "\n".join(lines)