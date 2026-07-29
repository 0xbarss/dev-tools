"""Optional `fzf` integration for interactive fuzzy-selection on top of
`grep`, `search`, and `project list`.

No hard dependency: if `fzf` isn't on `PATH`, callers fall back gracefully
with a clear hint instead of failing — same "sane defaults, no surprises"
philosophy as the rest of the toolkit (cf. `allow_network`).
"""

from __future__ import annotations

import shutil
import subprocess

NOT_INSTALLED_HINT = (
    "fzf not found on PATH — install it (e.g. `brew install fzf`, `apt install fzf`, "
    "or see https://github.com/junegunn/fzf#installation) to use --fzf. Falling back to normal output."
)


def fzf_available() -> bool:
    return shutil.which("fzf") is not None


def run_fzf(lines: list[str], multi: bool = True, prompt: str | None = None) -> list[str] | None:
    """Pipe `lines` through `fzf` for interactive fuzzy selection.

    Returns the selected line(s) verbatim, or `None` if fzf isn't installed,
    there was nothing to select from, or the user cancelled (Esc/Ctrl-C).
    Callers should format each line so the piece they care about (a path, a
    project name, ...) can be recovered afterward, since fzf hands back
    whole lines rather than structured data.
    """
    if not lines or not fzf_available():
        return None

    args = ["fzf"]
    if multi:
        args.append("--multi")
    if prompt:
        args.extend(["--prompt", prompt])

    try:
        result = subprocess.run(args, input="\n".join(lines), text=True, capture_output=True)
    except OSError:
        return None

    # fzf exit codes: 0 = selection made, 1 = no match, 130 = cancelled (Esc/Ctrl-C).
    if result.returncode != 0:
        return None

    selected = [line for line in result.stdout.splitlines() if line]
    return selected or None