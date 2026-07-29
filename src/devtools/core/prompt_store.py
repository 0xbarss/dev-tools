"""Storage and rendering for reusable AI prompt templates
(`devtools prompt list/run`, Prioritized Backlog: "Prompt template library", P3).

Templates are plain strings with `{variable}` placeholders (Python's
`str.format` mini-language), stored the same flat-JSON way as
`alias_store.py`. `render_template` is deliberately separate from any LLM
call: `devtools prompt run name` just prints the rendered text (so it can be
pasted into any AI tool) unless `--complete` asks it to also send the
rendered prompt through the configured `llm_client` -- matching the "explain
without one is still useful" ethos of `explain`/`context`.
"""

from __future__ import annotations

import json as _json
import re
import string
from dataclasses import dataclass
from pathlib import Path

try:
    import orjson
except ImportError:  # pragma: no cover
    orjson = None  # type: ignore[assignment]

from devtools.utils.paths import prompt_templates_file_path


class PromptRenderError(RuntimeError):
    """Raised when a template references a variable that wasn't supplied."""


@dataclass
class PromptTemplate:
    name: str
    template: str
    description: str = ""

    def to_dict(self) -> dict:
        return {"template": self.template, "description": self.description}

    @staticmethod
    def from_dict(name: str, data: dict) -> "PromptTemplate":
        return PromptTemplate(name=name, template=data.get("template", ""), description=data.get("description", "") or "")

    @property
    def variables(self) -> list[str]:
        formatter = string.Formatter()
        names = []
        for _, field_name, _, _ in formatter.parse(self.template):
            if field_name:
                names.append(field_name)
        return sorted(set(names))


def _dumps(obj) -> bytes:
    if orjson is not None:
        return orjson.dumps(obj, option=orjson.OPT_INDENT_2)
    return _json.dumps(obj, indent=2).encode("utf-8")


def _loads(data: bytes | str):
    if orjson is not None:
        return orjson.loads(data)
    return _json.loads(data)


def load_templates(path: Path | None = None) -> dict[str, PromptTemplate]:
    p = path or prompt_templates_file_path()
    if not p.is_file():
        return {}
    raw = _loads(p.read_bytes())
    return {name: PromptTemplate.from_dict(name, data) for name, data in raw.items()}


def save_templates(templates: dict[str, PromptTemplate], path: Path | None = None) -> Path:
    p = path or prompt_templates_file_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(_dumps({name: t.to_dict() for name, t in templates.items()}))
    return p


def add_template(name: str, template: str, description: str = "", path: Path | None = None) -> dict[str, PromptTemplate]:
    templates = load_templates(path)
    templates[name] = PromptTemplate(name=name, template=template, description=description)
    save_templates(templates, path)
    return templates


def remove_template(name: str, path: Path | None = None) -> bool:
    templates = load_templates(path)
    if name not in templates:
        return False
    del templates[name]
    save_templates(templates, path)
    return True


def render_template(template: PromptTemplate, variables: dict[str, str]) -> str:
    """Substitute `{var}` placeholders, raising a clear error naming exactly
    which variable is missing rather than surfacing a raw KeyError."""
    try:
        return template.template.format(**variables)
    except KeyError as exc:
        missing = exc.args[0]
        raise PromptRenderError(
            f"Template '{template.name}' requires variable '{missing}' -- pass it with --var {missing}=<value>."
        ) from exc


_VAR_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", re.DOTALL)


def parse_var_options(raw_vars: list[str]) -> dict[str, str]:
    """Parse repeatable `--var key=value` CLI options into a dict."""
    result: dict[str, str] = {}
    for raw in raw_vars:
        m = _VAR_RE.match(raw)
        if not m:
            raise ValueError(f"--var must be in the form key=value, got {raw!r}.")
        result[m.group(1)] = m.group(2)
    return result
