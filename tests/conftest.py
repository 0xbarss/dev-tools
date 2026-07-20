"""Shared pytest fixtures.

Every test gets an isolated ~/.config/devtools equivalent (via the
DEVTOOLS_CONFIG_DIR / DEVTOOLS_CACHE_DIR env var overrides that
devtools.utils.paths respects) so tests never touch the real user config,
and can run in parallel / any order.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated_devtools_home(tmp_path, monkeypatch):
    """Point devtools' config/cache dirs at a throwaway tmp_path for every test."""
    config_dir = tmp_path / "_devtools_config"
    cache_dir = tmp_path / "_devtools_cache"
    monkeypatch.setenv("DEVTOOLS_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("DEVTOOLS_CACHE_DIR", str(cache_dir))
    monkeypatch.delenv("DEVTOOLS_PROJECT", raising=False)
    yield {"config_dir": config_dir, "cache_dir": cache_dir}


@pytest.fixture
def sample_repo(tmp_path) -> Path:
    """A small, deterministic synthetic repo for unit tests (spec §11)."""
    root = tmp_path / "sample_repo"
    (root / "src").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "node_modules" / "pkg").mkdir(parents=True)
    (root / "__pycache__").mkdir()

    (root / "src" / "main.py").write_text("def main():\n    print('hello')\n\nif __name__ == '__main__':\n    main()\n")
    (root / "src" / "auth.py").write_text(
        "def login(user, password):\n"
        "    return authenticate(user, password)\n\n"
        "def authenticate(user, password):\n"
        "    return check_credential(user, password)\n\n"
        "def check_credential(user, password):\n"
        "    return True\n"
    )
    (root / "tests" / "test_auth.py").write_text("def test_login():\n    assert True\n")
    (root / "node_modules" / "pkg" / "index.js").write_text("module.exports = {};\n")
    (root / "__pycache__" / "main.cpython-312.pyc").write_bytes(b"\x00" * 32)
    (root / "pyproject.toml").write_text(
        '[project]\nname = "sample"\ndependencies = ["requests>=2.0", "flask>=2.0"]\n'
    )
    (root / "README.md").write_text("# sample\n\nA sample project.\n")
    (root / ".gitignore").write_text("*.log\n")
    (root / "debug.log").write_text("boot ok\n")
    return root


@pytest.fixture
def git_repo(sample_repo) -> Path:
    """sample_repo, initialized as a real git repository with one commit."""
    def _git(*args):
        subprocess.run(["git", *args], cwd=sample_repo, check=True, capture_output=True)

    _git("init", "-q")
    _git("config", "user.email", "test@example.com")
    _git("config", "user.name", "Test")
    _git("add", "-A")
    _git("commit", "-q", "-m", "initial commit")
    return sample_repo


@pytest.fixture
def big_repo(tmp_path) -> Path:
    """Generated (not committed) larger fixture for tree/stats/grep perf sanity checks."""
    root = tmp_path / "big_repo"
    for i in range(20):
        pkg = root / "src" / f"package_{i}"
        pkg.mkdir(parents=True)
        for j in range(15):
            (pkg / f"module_{j}.py").write_text(
                f"def func_{j}():\n    return {j}\n\nCONSTANT_{j} = {j}\n"
            )
    return root
