"""Loading, saving, and precedence resolution for devtools configuration.

Precedence (highest to lowest), per spec §10:

    CLI flags > DEVTOOLS_* env vars > --config override file >
    project-level overrides in config.toml > global defaults

`--config override file` replaces which *file* config.toml is read from, not
an extra layer on top of it — CLI flags and env vars still take precedence
over whatever that file contains.
"""

from __future__ import annotations

import os
from pathlib import Path

try:
    import tomllib  # Python >= 3.11
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]

try:
    import orjson
except ImportError:  # pragma: no cover
    orjson = None  # type: ignore[assignment]
import json as _json

from devtools.models.project import Project
from devtools.models.settings import Settings
from devtools.utils import paths as _paths

ENV_PREFIX = "DEVTOOLS_"


# --------------------------------------------------------------------------- #
# JSON helpers (orjson if available, stdlib json fallback otherwise)
# --------------------------------------------------------------------------- #


def _json_dumps(obj) -> bytes:
    if orjson is not None:
        return orjson.dumps(obj, option=orjson.OPT_INDENT_2)
    return _json.dumps(obj, indent=2).encode("utf-8")


def _json_loads(data: bytes | str):
    if orjson is not None:
        return orjson.loads(data)
    return _json.loads(data)


# --------------------------------------------------------------------------- #
# config.toml
# --------------------------------------------------------------------------- #


def load_settings(config_path: Path | None = None) -> Settings:
    path = config_path or _paths.config_file_path()
    if not path.is_file():
        return Settings()
    with path.open("rb") as f:
        raw = tomllib.load(f)
    return Settings.model_validate(raw)


def save_settings(settings: Settings, config_path: Path | None = None) -> Path:
    path = config_path or _paths.config_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_serialize_toml(settings), encoding="utf-8")
    return path


def _toml_scalar(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    raise TypeError(f"Unsupported TOML scalar type: {type(value)!r}")


def _toml_list(values: list) -> str:
    if not values:
        return "[]"
    items = ",\n    ".join(_toml_scalar(v) for v in values)
    return f"[\n    {items},\n]"


def _serialize_toml(settings: Settings) -> str:
    """Minimal, hand-rolled TOML serializer for our known Settings shape.

    We avoid a third-party TOML-writer dependency by only supporting the
    scalar/list/one-level-nested-table shape that Settings actually has.
    """
    lines: list[str] = []
    data = settings.model_dump(exclude={"project_overrides"})
    for key, value in data.items():
        if value is None:
            continue
        if isinstance(value, list):
            lines.append(f"{key} = {_toml_list(value)}")
        else:
            lines.append(f"{key} = {_toml_scalar(value)}")

    if settings.project_overrides:
        lines.append("")
        for name, override in settings.project_overrides.items():
            lines.append(f"[project_overrides.{name}]")
            lines.append(f"ignored_dirs = {_toml_list(override.ignored_dirs)}")
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


# --------------------------------------------------------------------------- #
# projects.json
# --------------------------------------------------------------------------- #


def load_projects(projects_path: Path | None = None) -> dict[str, Project]:
    path = projects_path or _paths.projects_file_path()
    if not path.is_file():
        return {}
    raw = _json_loads(path.read_bytes())
    return {name: Project(name=name, path=p) for name, p in raw.items()}


def save_projects(projects: dict[str, Project], projects_path: Path | None = None) -> Path:
    path = projects_path or _paths.projects_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    flat = {name: proj.path for name, proj in projects.items()}
    path.write_bytes(_json_dumps(flat))
    return path


# --------------------------------------------------------------------------- #
# Precedence resolution
# --------------------------------------------------------------------------- #


# --------------------------------------------------------------------------- #
# `devtools config get/set/list`
# --------------------------------------------------------------------------- #


class ConfigKeyError(KeyError):
    """Raised for an unrecognized or unsupported config key."""


def _parse_bool(raw: str) -> bool:
    lowered = raw.strip().lower()
    if lowered in ("true", "1", "yes", "on"):
        return True
    if lowered in ("false", "0", "no", "off"):
        return False
    raise ValueError(f"Not a boolean: {raw!r} (use true/false)")


def _parse_list(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def get_config_value(settings: Settings, key: str):
    """Read a config value by dotted key.

    Supports top-level Settings fields (`output_format`, `allow_network`,
    `ignored_dirs`, ...) and per-project overrides via
    `project_overrides.<name>.ignored_dirs`.
    """
    parts = key.split(".")
    if parts[0] == "project_overrides":
        if len(parts) != 3 or parts[2] != "ignored_dirs":
            raise ConfigKeyError(key)
        override = settings.project_overrides.get(parts[1])
        return override.ignored_dirs if override else []
    if len(parts) != 1 or not hasattr(settings, parts[0]) or parts[0] == "project_overrides":
        raise ConfigKeyError(key)
    return getattr(settings, parts[0])


def set_config_value(settings: Settings, key: str, raw_value: str) -> None:
    """Set a config value by dotted key (same key space as `get_config_value`),
    coercing `raw_value` to match the existing field's type. Mutates `settings`
    in place; caller is responsible for persisting via `save_settings`."""
    from devtools.models.settings import ProjectOverride

    parts = key.split(".")
    if parts[0] == "project_overrides":
        if len(parts) != 3 or parts[2] != "ignored_dirs":
            raise ConfigKeyError(key)
        proj_name = parts[1]
        override = settings.project_overrides.setdefault(proj_name, ProjectOverride())
        override.ignored_dirs = _parse_list(raw_value)
        return

    if len(parts) != 1 or not hasattr(settings, parts[0]):
        raise ConfigKeyError(key)
    field_name = parts[0]
    current = getattr(settings, field_name)

    if isinstance(current, bool):
        setattr(settings, field_name, _parse_bool(raw_value))
    elif isinstance(current, list):
        setattr(settings, field_name, _parse_list(raw_value))
    else:
        # Covers str fields and None-defaulting Optional[str] fields
        # (e.g. default_project) alike.
        setattr(settings, field_name, raw_value)


def all_config_values(settings: Settings) -> dict:
    """Flat dict of every gettable config value, for `devtools config list`."""
    data = settings.model_dump(exclude={"project_overrides"})
    for proj_name, override in settings.project_overrides.items():
        data[f"project_overrides.{proj_name}.ignored_dirs"] = override.ignored_dirs
    return data


def resolve_project_name(
    cli_project: str | None,
    settings: Settings,
    projects: dict[str, Project],
    cwd: Path | None = None,
) -> str | None:
    """CLI arg -> DEVTOOLS_PROJECT env var -> configured default -> cwd match."""
    if cli_project:
        return cli_project
    env_project = os.environ.get(f"{ENV_PREFIX}PROJECT")
    if env_project:
        return env_project
    if settings.default_project:
        return settings.default_project
    cwd = cwd or Path.cwd()
    for name, proj in projects.items():
        if proj.resolved_path.resolve() == cwd.resolve():
            return name
    return None


def env_override(key: str) -> str | None:
    """Read a DEVTOOLS_<KEY> env var, e.g. env_override('OUTPUT_FORMAT')."""
    return os.environ.get(f"{ENV_PREFIX}{key.upper()}")