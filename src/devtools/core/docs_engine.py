"""`devtools docs generate` — fill missing README sections (proposal §4,
backlog #23, P2).

`doctor` already detects a missing README (`check_missing_readme`) and can
stub one out under `--fix` (`doctor_checks._README_STUB_TEMPLATE`). This
module is the AI-assisted upgrade of that same gap: when an AI provider is
configured, it drafts real content (using a light repo scan — manifests +
top-level structure — as grounding); with no provider configured, it falls
back to the same deterministic stub `doctor --fix` already uses, so `docs
generate` is never a hard failure just because AI isn't set up.
"""

from __future__ import annotations

from pathlib import Path

from devtools.core.deps_engine import analyze as analyze_dependencies
from devtools.core.doctor_checks import _README_STUB_TEMPLATE
from devtools.core.ignore_rules import IgnoreRules
from devtools.core.llm_client import LLMClient, NoneClient
from devtools.core.tree_engine import build_tree, render_lines

_SYSTEM_PROMPT = (
    "You are drafting a README.md for a software project, given its directory tree "
    "and detected dependency manifests. Write clear, concrete Markdown with these "
    "sections: a one-paragraph description, Installation, Usage (with a small example "
    "if you can infer one), and a short Configuration section if relevant. Don't "
    "invent specific commands/APIs you can't infer from the given structure -- prefer "
    "a TODO placeholder over a plausible-sounding fabrication. No preamble, just the "
    "README content starting at the title heading."
)

_MAX_TREE_DEPTH = 3


def generate_readme(root: Path, ignore_rules: IgnoreRules, client: LLMClient, project_name: str) -> tuple[str, bool]:
    """Returns (content, ai_generated). Falls back to the deterministic
    stub template (same one `doctor --fix` uses) if no AI provider is
    configured, so this command is always usable."""
    if isinstance(client, NoneClient):
        return _README_STUB_TEMPLATE.format(title=project_name), False

    tree = build_tree(root, ignore_rules, max_depth=_MAX_TREE_DEPTH)
    tree_text = "\n".join(render_lines(tree))
    deps = analyze_dependencies(root)
    ecosystem_lines = []
    for eco_name, deps_list in deps.by_ecosystem().items():
        names = ", ".join(sorted({d.name for d in deps_list})[:20])
        ecosystem_lines.append(f"- {eco_name}: {names}")
    deps_text = "\n".join(ecosystem_lines) if ecosystem_lines else "(no dependency manifests detected)"

    prompt = (
        f"Project name: {project_name}\n\n"
        f"Directory tree (depth {_MAX_TREE_DEPTH}):\n```\n{tree_text}\n```\n\n"
        f"Detected dependencies:\n{deps_text}\n"
    )
    content = client.complete(prompt, system=_SYSTEM_PROMPT)
    return content, True
