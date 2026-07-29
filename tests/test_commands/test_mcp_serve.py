from __future__ import annotations

import asyncio
import json

import pytest

pytest.importorskip("mcp")

from devtools.core import config as cfgmod
from devtools.commands.mcp_serve import build_server


def _register_project(tmp_path, name, root):
    projects = cfgmod.load_projects()
    from devtools.models.project import Project

    projects[name] = Project(name=name, path=str(root))
    cfgmod.save_projects(projects)


def test_build_server_registers_expected_tools(sample_repo):
    _register_project(sample_repo, "mcp_demo", sample_repo)
    server = build_server()

    async def _list():
        return await server.list_tools()

    tools = asyncio.run(_list())
    names = {t.name for t in tools}
    assert {"list_projects", "stats", "tree", "doctor", "deps", "grep", "search", "lint", "context", "explain", "changelog"} <= names


def test_stats_tool_returns_real_data(sample_repo):
    _register_project(sample_repo, "mcp_stats_demo", sample_repo)
    server = build_server()

    async def _call():
        return await server.call_tool("stats", {"project": "mcp_stats_demo"})

    content = asyncio.run(_call())
    payload = json.loads(content[0].text)
    assert payload["file_count"] > 0


def test_unregistered_project_returns_clear_error(sample_repo):
    server = build_server()

    async def _call():
        return await server.call_tool("stats", {"project": "definitely-not-registered"})

    with pytest.raises(Exception, match="not registered"):
        asyncio.run(_call())