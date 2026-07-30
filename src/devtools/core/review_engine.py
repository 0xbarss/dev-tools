"""`devtools review` — local PR/diff review assistant (proposal deep-dive #4).

Combines `collect`'s existing git-aware diffing (`utils/git.py`) with the
`core/llm_client.py` abstraction. The proposal itself flags the risk of
"shallow/noisy AI review commentary" — this module ships with an explicit
"suggestions, not blockers" framing in both the system prompt and the
rendered output, and degrades gracefully to a raw-text review if the model
doesn't return well-formed JSON.
"""

from __future__ import annotations

import json as _json
from dataclasses import dataclass, field
from pathlib import Path

from devtools.core.llm_client import LLMClient
from devtools.utils import git as gitutil

_SYSTEM_PROMPT = (
    "You are reviewing a git diff as a helpful, low-ego senior engineer. "
    "These are suggestions, not blockers — the author decides what to act on. "
    "Focus on real bugs, missing tests, and unclear naming/structure; skip "
    "nitpicks a formatter/linter would already catch. "
    "Respond with ONLY a JSON object of the shape: "
    '{"summary": "<2-3 sentence overview>", "comments": '
    '[{"file": "path", "line": <int or null>, "severity": "bug|style|missing_test|question", '
    '"comment": "<one or two sentences>"}]}. No prose outside the JSON.'
)

_SECURITY_SYSTEM_PROMPT = (
    "You are doing a SECURITY-focused review of a git diff, as an advisory pass only "
    "(a separate, deterministic pattern-based scan already ran and is reported alongside "
    "yours — don't repeat obvious secret/eval/pickle findings, focus on things pattern "
    "matching can't catch: auth/authorization logic, injection via non-obvious paths, "
    "unsafe deserialization patterns, missing input validation, insecure defaults). "
    "Be clear this is advisory, not a certification of security. "
    "Respond with ONLY a JSON object of the shape: "
    '{"summary": "<2-3 sentence overview>", "comments": '
    '[{"file": "path", "line": <int or null>, "severity": "bug|style|missing_test|question", '
    '"comment": "<one or two sentences>"}]}. No prose outside the JSON.'
)

_MAX_DIFF_CHARS = 60_000


@dataclass
class ReviewComment:
    file: str
    line: int | None
    severity: str
    comment: str


@dataclass
class ReviewReport:
    since: str
    summary: str
    comments: list[ReviewComment] = field(default_factory=list)
    raw_text: str | None = None  # populated only if JSON parsing failed


def _extract_json_object(text: str) -> dict | None:
    text = text.strip()
    # Strip a ```json ... ``` fence if the model wrapped its answer in one.
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


def review(root: Path, client: LLMClient, since: str, paths: list[str] | None = None, security: bool = False) -> ReviewReport:
    diff = gitutil.diff_since(root, since, paths=paths)
    if not diff.strip():
        raise ValueError(f"No changes since '{since}' — nothing to review.")
    if len(diff) > _MAX_DIFF_CHARS:
        diff = diff[:_MAX_DIFF_CHARS] + "\n... (diff truncated for length) ..."

    prompt = f"Review this diff (against `{since}`):\n\n```diff\n{diff}\n```"
    system_prompt = _SECURITY_SYSTEM_PROMPT if security else _SYSTEM_PROMPT
    response = client.complete(prompt, system=system_prompt)

    parsed = _extract_json_object(response)
    if parsed is None:
        return ReviewReport(since=since, summary="(unstructured response — see raw_text)", raw_text=response)

    comments = [
        ReviewComment(
            file=c.get("file", ""),
            line=c.get("line"),
            severity=c.get("severity", "question"),
            comment=c.get("comment", ""),
        )
        for c in parsed.get("comments", [])
        if isinstance(c, dict)
    ]
    return ReviewReport(since=since, summary=parsed.get("summary", ""), comments=comments)


def render_markdown(report: ReviewReport, project_name: str) -> str:
    lines = [f"# Review — {project_name} (since `{report.since}`)", "", "_Suggestions, not blockers._", ""]
    lines.append(report.summary)
    lines.append("")
    if report.raw_text:
        lines.append("## Raw model output")
        lines.append("")
        lines.append(report.raw_text)
        return "\n".join(lines)
    if not report.comments:
        lines.append("No specific comments.")
        return "\n".join(lines)
    lines.append("## Comments")
    lines.append("")
    for c in report.comments:
        loc = f"{c.file}:{c.line}" if c.line else c.file
        lines.append(f"- **[{c.severity}]** `{loc}` — {c.comment}")
    return "\n".join(lines)
