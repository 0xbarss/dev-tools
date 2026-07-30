"""`devtools commit explain <sha>` — natural-language commit explainer
(backlog #26, P2). A small, one-commit-scoped sibling of `devtools
explain` (which explains a file/symbol) and `devtools review` (which
reviews a range of changes): this explains exactly one commit's patch in
plain English, good for changelog/onboarding context ("what did this
commit actually do and why").
"""

from __future__ import annotations

from pathlib import Path

from devtools.core.llm_client import LLMClient
from devtools.utils import git as gitutil

_SYSTEM_PROMPT = (
    "You are explaining a single git commit to a teammate who wasn't there when it "
    "was made. Given the commit message and its patch, explain in plain English: "
    "(1) what changed, (2) why it likely changed (infer from the message/diff if not "
    "explicit), (3) anything that looks risky or worth double-checking. Be concise -- "
    "a short paragraph or a few bullets, not an essay."
)

_MAX_PATCH_CHARS = 40_000


def explain_commit(root: Path, sha: str, client: LLMClient) -> str:
    commit = gitutil.show_commit(root, sha)
    patch = commit["patch"]
    if len(patch) > _MAX_PATCH_CHARS:
        patch = patch[:_MAX_PATCH_CHARS] + "\n... (patch truncated for length) ..."

    prompt = (
        f"Commit {commit['short_hash']} by {commit['author_name']} ({commit['date']}):\n\n"
        f"Subject: {commit['subject']}\n"
        f"{commit['body']}\n\n"
        f"Patch:\n```diff\n{patch}\n```"
    )
    return client.complete(prompt, system=_SYSTEM_PROMPT)
