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


def rag_index_db_path(project_name: str) -> Path:
    """Where the persistent, chunk-level RAG index (proposal deep-dive #25,
    `devtools ask` / `devtools index build --rag`) is stored -- deliberately
    a separate database file from `index_db_path`'s whole-file index, since
    the two have different schemas (whole-file vectors vs. chunked text +
    vectors) and independent lifecycles."""
    return index_dir() / f"{project_name}_rag.sqlite3"


def notify_targets_file_path() -> Path:
    """Where configured notification webhook targets (`devtools notify`) live."""
    return config_dir() / "notifications.json"


def marketplace_custom_file_path() -> Path:
    """User-added marketplace entries (`devtools marketplace add`), layered on
    top of the bundled curated registry."""
    return config_dir() / "marketplace_custom.json"


def plugins_dir() -> Path:
    """Where single-file script plugins installed via `devtools plugin
    install ./my-check.py` are copied (the "config-only"/simple tier --
    proper packages register through Python entry points instead and
    never touch this directory)."""
    return config_dir() / "plugins"


def bookmarks_file_path() -> Path:
    """Named quick-jumps within projects (`devtools bookmark`, backlog #37)."""
    return config_dir() / "bookmarks.json"


def snippets_file_path() -> Path:
    """Small reusable code snippets (`devtools snippet`, backlog #34)."""
    return config_dir() / "snippets.json"


def saved_searches_file_path() -> Path:
    """Named, re-runnable `devtools search` queries (backlog #38)."""
    return config_dir() / "saved_searches.json"


def prompt_templates_file_path() -> Path:
    """User-defined reusable AI prompt templates (`devtools prompt`, backlog #31)."""
    return config_dir() / "prompt_templates.json"


def snapshots_file_path() -> Path:
    """Saved workspace snapshots (`devtools snapshot`, backlog #32)."""
    return config_dir() / "snapshots.json"


def daemon_dir() -> Path:
    """Where per-project daemon pidfiles/logs (`devtools daemon`, backlog #51) live."""
    override = os.environ.get("DEVTOOLS_DAEMON_DIR")
    if override:
        return Path(override).expanduser()
    return cache_dir() / "daemon"


def daemon_pid_file_path(project_name: str) -> Path:
    return daemon_dir() / f"{project_name}.pid"


def daemon_log_file_path(project_name: str) -> Path:
    return daemon_dir() / f"{project_name}.log"
