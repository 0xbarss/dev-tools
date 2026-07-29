from __future__ import annotations

from pathlib import Path

from devtools.core import config as cfgmod
from devtools.models.project import Project
from devtools.models.settings import DEFAULT_IGNORED_DIRS, ProjectOverride, Settings


def test_settings_roundtrip_via_toml(tmp_path):
    path = tmp_path / "config.toml"
    settings = Settings(
        default_project="api",
        allow_network=True,
        project_overrides={"api": ProjectOverride(ignored_dirs=["legacy/"])},
    )
    cfgmod.save_settings(settings, path)
    loaded = cfgmod.load_settings(path)

    assert loaded.default_project == "api"
    assert loaded.allow_network is True
    # ignored_dirs is additive: the full global default list, plus any
    # per-project override entries appended (see Settings.ignored_dirs_for).
    assert loaded.ignored_dirs_for("api") == [*DEFAULT_IGNORED_DIRS, "legacy/"]
    assert loaded.ignored_dirs_for("unknown_project") == DEFAULT_IGNORED_DIRS


def test_load_settings_missing_file_returns_defaults(tmp_path):
    settings = cfgmod.load_settings(tmp_path / "does_not_exist.toml")
    assert settings.output_format == "markdown"
    assert settings.allow_network is False


def test_projects_roundtrip_via_json(tmp_path):
    path = tmp_path / "projects.json"
    projects = {
        "api": Project(name="api", path=str(tmp_path / "api")),
        "blog": Project(name="blog", path=str(tmp_path / "blog")),
    }
    cfgmod.save_projects(projects, path)
    loaded = cfgmod.load_projects(path)
    assert set(loaded) == {"api", "blog"}
    assert loaded["api"].path == str(Path(tmp_path / "api"))


def test_project_path_is_expanded():
    proj = Project(name="x", path="~/Projects/API")
    assert "~" not in proj.path


def test_resolve_project_name_precedence(tmp_path, monkeypatch):
    settings = Settings(default_project="api")
    projects = {
        "api": Project(name="api", path=str(tmp_path)),
        "blog": Project(name="blog", path=str(tmp_path / "blog")),
    }

    # CLI arg wins over everything
    assert cfgmod.resolve_project_name("blog", settings, projects) == "blog"

    # env var wins over default
    monkeypatch.setenv("DEVTOOLS_PROJECT", "blog")
    assert cfgmod.resolve_project_name(None, settings, projects) == "blog"
    monkeypatch.delenv("DEVTOOLS_PROJECT")

    # falls back to configured default
    assert cfgmod.resolve_project_name(None, settings, projects) == "api"

    # falls back to cwd match when no default is configured
    settings_no_default = Settings()
    assert cfgmod.resolve_project_name(None, settings_no_default, projects, cwd=tmp_path) == "api"
