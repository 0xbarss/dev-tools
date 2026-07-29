from __future__ import annotations

import pytest

from devtools.core.config import ConfigKeyError, all_config_values, get_config_value, set_config_value
from devtools.models.settings import Settings


def test_get_config_value_top_level_scalar():
    settings = Settings()
    assert get_config_value(settings, "allow_network") is False
    assert get_config_value(settings, "output_format") == "markdown"


def test_get_config_value_list_field():
    settings = Settings()
    assert ".git" in get_config_value(settings, "ignored_dirs")


def test_get_config_value_unknown_key_raises():
    settings = Settings()
    with pytest.raises(ConfigKeyError):
        get_config_value(settings, "not_a_real_key")


def test_set_config_value_bool_coercion():
    settings = Settings()
    set_config_value(settings, "allow_network", "true")
    assert settings.allow_network is True
    set_config_value(settings, "allow_network", "false")
    assert settings.allow_network is False


def test_set_config_value_bool_rejects_garbage():
    settings = Settings()
    with pytest.raises(ValueError):
        set_config_value(settings, "allow_network", "maybe")


def test_set_config_value_list_coercion():
    settings = Settings()
    set_config_value(settings, "ignored_dirs", "foo, bar,  baz")
    assert settings.ignored_dirs == ["foo", "bar", "baz"]


def test_set_config_value_string_field():
    settings = Settings()
    set_config_value(settings, "default_project", "api")
    assert settings.default_project == "api"


def test_set_config_value_unknown_key_raises():
    settings = Settings()
    with pytest.raises(ConfigKeyError):
        set_config_value(settings, "nope", "x")


def test_project_override_ignored_dirs_roundtrip():
    settings = Settings()
    set_config_value(settings, "project_overrides.api.ignored_dirs", "fixtures, tmp")
    assert get_config_value(settings, "project_overrides.api.ignored_dirs") == ["fixtures", "tmp"]


def test_project_override_get_missing_project_returns_empty():
    settings = Settings()
    assert get_config_value(settings, "project_overrides.ghost.ignored_dirs") == []


def test_all_config_values_includes_project_overrides():
    settings = Settings()
    set_config_value(settings, "project_overrides.api.ignored_dirs", "fixtures")
    values = all_config_values(settings)
    assert values["project_overrides.api.ignored_dirs"] == ["fixtures"]
    assert "output_format" in values