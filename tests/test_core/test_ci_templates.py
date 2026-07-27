from __future__ import annotations

import pytest

from devtools.core.ci_templates import render_ci_config


def test_render_github_config():
    path, content = render_ci_config("github", "myproj")
    assert path == ".github/workflows/devtools.yml"
    assert "devtools project add myproj . --force" in content
    assert "devtools doctor myproj --ci" in content
    assert "devtools deps myproj --check" in content


def test_render_gitlab_config():
    path, content = render_ci_config("gitlab", "myproj")
    assert path == ".gitlab-ci.yml"
    assert "devtools project add myproj . --force" in content
    assert "devtools doctor myproj --ci" in content


def test_render_ci_config_unknown_provider_raises():
    with pytest.raises(ValueError):
        render_ci_config("bamboo", "myproj")
