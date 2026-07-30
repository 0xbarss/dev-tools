"""`devtools plugin` — third-party/user command extension points (backlog
#8, P1).

Two tiers, matching the proposal's own tradeoff discussion:

1. **Entry-point plugins** (full code, full privileges): a proper Python
   package declares a `devtools.plugins` entry point pointing at a module
   that exposes `register(app: typer.Typer) -> None`. Discovered via
   stdlib `importlib.metadata` -- no custom loader, and additive to
   `cli.py`'s existing hard-registration (nothing about the current
   command wiring has to change for this to work). Install/removal is
   just `pip install`/`pip uninstall` of that package; devtools doesn't
   reimplement a package manager.

2. **Script plugins** (the "config-only"-adjacent lighter tier): a single
   `.py` file with the same `register(app)` contract, copied into
   `<config_dir>/plugins/` via `devtools plugin install ./my-check.py`
   with no packaging required. Still arbitrary code with full process
   privileges -- there is no sandboxing here, and `devtools plugin list`
   says so explicitly rather than implying a safety guarantee this system
   doesn't provide.

Either tier may declare a module-level `DEVTOOLS_API_VERSION` string; a
mismatch with `CURRENT_API_VERSION` is reported, not fatal -- the plugin
still loads (its author gets to decide what that means for their own
commands), consistent with "flag incompatible ones rather than crashing."
"""

from __future__ import annotations

import importlib.util
import shutil
from dataclasses import dataclass
from importlib.metadata import EntryPoint, entry_points
from pathlib import Path
from types import ModuleType

import typer

from devtools.utils.paths import plugins_dir

ENTRY_POINT_GROUP = "devtools.plugins"
CURRENT_API_VERSION = "1"


class PluginError(Exception):
    pass


@dataclass
class PluginInfo:
    name: str
    source: str  # "entry_point" | "script"
    location: str  # "module:attr" for entry points, file path for scripts
    api_version: str | None = None
    loaded: bool = False
    error: str | None = None

    @property
    def api_compatible(self) -> bool | None:
        if self.api_version is None:
            return None
        return self.api_version == CURRENT_API_VERSION


def _load_script_module(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"devtools_plugin_{path.stem}", path)
    if spec is None or spec.loader is None:
        raise PluginError(f"Could not load '{path}' as a Python module.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _resolve_entry_point_module(ep: EntryPoint) -> tuple[ModuleType | None, object]:
    """Returns (module_or_None, register_callable). If the entry point
    value points directly at a callable (e.g. "pkg.plugin:register"),
    there's no module to read DEVTOOLS_API_VERSION from -- that's fine,
    api_version just stays unknown for that plugin."""
    loaded = ep.load()
    if isinstance(loaded, ModuleType):
        register = getattr(loaded, "register", None)
        if register is None:
            raise PluginError(f"Entry point '{ep.name}' -> '{ep.value}' has no register(app) function.")
        return loaded, register
    if callable(loaded):
        return None, loaded
    raise PluginError(f"Entry point '{ep.name}' -> '{ep.value}' is neither a module nor a callable.")


def list_entry_point_plugins() -> list[PluginInfo]:
    infos = []
    for ep in entry_points(group=ENTRY_POINT_GROUP):
        info = PluginInfo(name=ep.name, source="entry_point", location=ep.value)
        try:
            module, _register = _resolve_entry_point_module(ep)
            if module is not None:
                info.api_version = getattr(module, "DEVTOOLS_API_VERSION", None)
        except Exception as exc:  # noqa: BLE001 - a broken plugin shouldn't crash discovery
            info.error = str(exc)
        infos.append(info)
    return infos


def list_script_plugins() -> list[PluginInfo]:
    directory = plugins_dir()
    if not directory.is_dir():
        return []
    infos = []
    for path in sorted(directory.glob("*.py")):
        info = PluginInfo(name=path.stem, source="script", location=str(path))
        try:
            module = _load_script_module(path)
            if not hasattr(module, "register"):
                raise PluginError("missing register(app) function")
            info.api_version = getattr(module, "DEVTOOLS_API_VERSION", None)
        except Exception as exc:  # noqa: BLE001 - reported per-plugin, not raised
            info.error = str(exc)
        infos.append(info)
    return infos


def list_plugins() -> list[PluginInfo]:
    return [*list_entry_point_plugins(), *list_script_plugins()]


def install_script_plugin(path: Path) -> PluginInfo:
    if not path.is_file() or path.suffix != ".py":
        raise PluginError(f"'{path}' is not a .py file. For a proper package with a pyproject.toml, `pip install` it instead.")
    try:
        module = _load_script_module(path)
    except Exception as exc:  # noqa: BLE001
        raise PluginError(f"'{path}' failed to import: {exc}") from exc
    if not hasattr(module, "register"):
        raise PluginError(f"'{path}' has no register(app) function -- see `devtools plugin install --help`.")

    directory = plugins_dir()
    directory.mkdir(parents=True, exist_ok=True)
    dest = directory / path.name
    shutil.copy2(path, dest)
    return PluginInfo(
        name=dest.stem,
        source="script",
        location=str(dest),
        api_version=getattr(module, "DEVTOOLS_API_VERSION", None),
    )


def remove_script_plugin(name: str) -> bool:
    directory = plugins_dir()
    path = directory / f"{name}.py"
    if not path.exists():
        return False
    path.unlink()
    return True


def load_all_plugins(app: typer.Typer) -> list[PluginInfo]:
    """Registers every discoverable plugin's commands onto `app`. Called
    once from `cli.py` after all built-in commands are wired up. Each
    plugin is isolated in its own try/except -- one broken or malicious
    plugin reports as failed-to-load rather than taking down the whole
    CLI for every other command."""
    results: list[PluginInfo] = []

    for ep in entry_points(group=ENTRY_POINT_GROUP):
        info = PluginInfo(name=ep.name, source="entry_point", location=ep.value)
        try:
            module, register = _resolve_entry_point_module(ep)
            if module is not None:
                info.api_version = getattr(module, "DEVTOOLS_API_VERSION", None)
            register(app)
            info.loaded = True
        except Exception as exc:  # noqa: BLE001
            info.error = str(exc)
        results.append(info)

    directory = plugins_dir()
    if directory.is_dir():
        for path in sorted(directory.glob("*.py")):
            info = PluginInfo(name=path.stem, source="script", location=str(path))
            try:
                module = _load_script_module(path)
                info.api_version = getattr(module, "DEVTOOLS_API_VERSION", None)
                if not hasattr(module, "register"):
                    raise PluginError("missing register(app) function")
                module.register(app)
                info.loaded = True
            except Exception as exc:  # noqa: BLE001
                info.error = str(exc)
            results.append(info)

    return results
