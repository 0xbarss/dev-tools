"""Cross-platform config/cache directory resolution.

We intentionally use a fixed app name/author pair so that on every platform
the same folder is used regardless of how devtools was invoked. On Linux this
resolves to ~/.config/devtools, matching the spec exactly; on macOS/Windows
platformdirs picks the OS-appropriate equivalent.
"""

from __future__ import annotations

import os
from pathlib import Path

from platformdirs import PlatformDirs

_dirs = PlatformDirs(appname="devtools", appauthor=False, roaming=False)


def config_dir() -> Path:
    """Root config directory, e.g. ~/.config/devtools on Linux."""
    override = os.environ.get("DEVTOOLS_CONFIG_DIR")
    if override:
        return Path(override).expanduser()
    return Path(_dirs.user_config_dir)


def cache_dir() -> Path:
    override = os.environ.get("DEVTOOLS_CACHE_DIR")
    if override:
        return Path(override).expanduser()
    return Path(_dirs.user_cache_dir)


def config_file_path() -> Path:
    return config_dir() / "config.toml"


def projects_file_path() -> Path:
    return config_dir() / "projects.json"


def history_file_path() -> Path:
    return config_dir() / "history.jsonl"


def aliases_file_path() -> Path:
    return config_dir() / "aliases.json"


def ensure_config_dir() -> Path:
    d = config_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d


def index_dir() -> Path:
    """Where per-project SQLite indexes (spec proposal #1/#50) are stored."""
    override = os.environ.get("DEVTOOLS_INDEX_DIR")
    if override:
        return Path(override).expanduser()
    return cache_dir() / "index"


def index_db_path(project_name: str) -> Path:
    return index_dir() / f"{project_name}.sqlite3"


def notify_targets_file_path() -> Path:
    """Where configured notification webhook targets (`devtools notify`) live."""
    return config_dir() / "notifications.json"


def marketplace_custom_file_path() -> Path:
    """User-added marketplace entries (`devtools marketplace add`), layered on
    top of the bundled curated registry."""
    return config_dir() / "marketplace_custom.json"
