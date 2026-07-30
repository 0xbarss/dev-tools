"""`devtools run <task>` — a task-runner front-end (backlog #40, P2): one
command that finds a task by name across whichever of Makefile, `npm`/
`package.json` scripts, and `justfile` are present, so you don't need to
remember which one this particular repo uses.

Read-only detection + a single subprocess invocation of the underlying
tool (`make`, `npm run`, or `just`) -- this never re-implements what those
tools do, only which one to call.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

_MAKE_TARGET_RE = re.compile(r"^([a-zA-Z0-9][a-zA-Z0-9_.\-]*)\s*:(?!=)")
_JUST_RECIPE_RE = re.compile(r"^([a-zA-Z0-9_\-]+)(\s+[^:]*)?:(?!=)")


@dataclass
class Task:
    name: str
    source: str  # "make" | "npm" | "just"
    command: str  # human-readable, for `devtools run --list`


def _discover_make_tasks(root: Path) -> list[Task]:
    makefile = next((root / name for name in ("Makefile", "makefile") if (root / name).is_file()), None)
    if makefile is None:
        return []
    tasks = []
    seen = set()
    for line in makefile.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("\t") or line.startswith("#"):
            continue
        match = _MAKE_TARGET_RE.match(line)
        if not match:
            continue
        name = match.group(1)
        if name.startswith(".") or name in seen:  # .PHONY, .DEFAULT, etc.
            continue
        seen.add(name)
        tasks.append(Task(name=name, source="make", command=f"make {name}"))
    return tasks


def _discover_npm_tasks(root: Path) -> list[Task]:
    package_json = root / "package.json"
    if not package_json.is_file():
        return []
    import json

    try:
        data = json.loads(package_json.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    scripts = data.get("scripts") or {}
    return [Task(name=name, source="npm", command=f"npm run {name}") for name in scripts]


def _discover_just_tasks(root: Path) -> list[Task]:
    justfile = next((root / name for name in ("justfile", "Justfile") if (root / name).is_file()), None)
    if justfile is None:
        return []
    tasks = []
    for line in justfile.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith((" ", "\t", "#", "@")):
            continue
        match = _JUST_RECIPE_RE.match(line)
        if not match:
            continue
        name = match.group(1)
        tasks.append(Task(name=name, source="just", command=f"just {name}"))
    return tasks


def discover_tasks(root: Path) -> list[Task]:
    """All tasks found across Makefile, package.json scripts, and justfile,
    in that priority order (later sources' same-named task is still listed
    separately -- ambiguity is surfaced, not silently resolved)."""
    return _discover_make_tasks(root) + _discover_npm_tasks(root) + _discover_just_tasks(root)


def find_task(root: Path, name: str) -> list[Task]:
    """All tasks matching `name` (usually one, but could be >1 if e.g. both
    a Makefile and package.json define the same task name -- the caller
    decides how to handle that ambiguity)."""
    return [t for t in discover_tasks(root) if t.name == name]


def run_task(root: Path, task: Task) -> int:
    """Runs the task, streaming its output straight to the terminal
    (not captured) since task output — test runs, builds — is meant to be
    watched live, not parsed. Returns the child process's exit code."""
    if task.source == "make":
        cmd = ["make", task.name]
    elif task.source == "npm":
        cmd = ["npm", "run", task.name]
    elif task.source == "just":
        cmd = ["just", task.name]
    else:  # pragma: no cover — defensive, discover_tasks only emits the above
        raise ValueError(f"Unknown task source '{task.source}'")
    proc = subprocess.run(cmd, cwd=root)
    return proc.returncode
