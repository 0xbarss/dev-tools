"""Storage for user-defined aliases (`devtools alias add/run/list`).

Aliases are stored as raw shell-like command strings, e.g.
"stats api && doctor api" — `alias run` splits on `&&` and re-invokes the
`devtools` entry point for each piece via subprocess, so aliases compose
ordinary devtools commands rather than arbitrary shell.
"""

from __future__ import annotations

import json as _json
from pathlib import Path

try:
    import orjson
except ImportError:  # pragma: no cover
    orjson = None  # type: ignore[assignment]

from devtools.utils.paths import aliases_file_path


def _dumps(obj) -> bytes:
    if orjson is not None:
        return orjson.dumps(obj, option=orjson.OPT_INDENT_2)
    return _json.dumps(obj, indent=2).encode("utf-8")


def load_aliases(path: Path | None = None) -> dict[str, str]:
    p = path or aliases_file_path()
    if not p.is_file():
        return {}
    raw = p.read_bytes()
    return orjson.loads(raw) if orjson is not None else _json.loads(raw)


def save_aliases(aliases: dict[str, str], path: Path | None = None) -> Path:
    p = path or aliases_file_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(_dumps(aliases))
    return p


def add_alias(name: str, command: str, path: Path | None = None) -> dict[str, str]:
    aliases = load_aliases(path)
    aliases[name] = command
    save_aliases(aliases, path)
    return aliases


def remove_alias(name: str, path: Path | None = None) -> bool:
    aliases = load_aliases(path)
    if name not in aliases:
        return False
    del aliases[name]
    save_aliases(aliases, path)
    return True


def split_chain(command: str) -> list[list[str]]:
    """Split an alias's stored command string on `&&` into argv lists.

    "stats api && doctor api" -> [["stats", "api"], ["doctor", "api"]]
    """
    import shlex

    return [shlex.split(part.strip()) for part in command.split("&&") if part.strip()]


def parse_pipeline(command: str) -> list[list[list[str]]]:
    """Parse an alias command string into sequential stages, each of which
    may itself be a `|`-connected pipe chain.

    `&&` still means "run next step only if the previous succeeded" (same as
    `split_chain`); `|` within a step means "feed this step's stdout into the
    next step's stdin", same as a shell pipe.

    "stats api && grep api TODO | grep -v test" ->
    [
        [["stats", "api"]],
        [["grep", "api", "TODO"], ["grep", "-v", "test"]],
    ]
    """
    import shlex

    sequential_parts = [p.strip() for p in command.split("&&") if p.strip()]
    pipeline: list[list[list[str]]] = []
    for part in sequential_parts:
        stages = [shlex.split(stage.strip()) for stage in part.split("|") if stage.strip()]
        pipeline.append(stages)
    return pipeline
