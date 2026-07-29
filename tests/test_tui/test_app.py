from __future__ import annotations

import asyncio

from devtools.core import config as cfgmod
from devtools.models.project import Project
from devtools.tui.app import DashboardScreen, DevtoolsApp, ProjectListScreen


def run_async(coro):
    return asyncio.run(coro)


def _register(name: str, path) -> None:
    cfgmod.save_projects({name: Project(name=name, path=str(path))})


def test_project_list_screen_shows_empty_state_when_no_projects():
    async def scenario():
        app = DevtoolsApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, ProjectListScreen)
            list_view = screen.query_one("#project-list")
            assert len(list_view.children) == 1  # the "no projects" placeholder item

    run_async(scenario())


def test_project_list_screen_lists_registered_projects(sample_repo):
    _register("demo", sample_repo)

    async def scenario():
        app = DevtoolsApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            screen = app.screen
            list_view = screen.query_one("#project-list")
            item_ids = [child.id for child in list_view.children]
            assert "proj-demo" in item_ids

    run_async(scenario())


def test_selecting_a_project_pushes_dashboard_screen(sample_repo):
    _register("demo", sample_repo)

    async def scenario():
        app = DevtoolsApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            list_view = app.screen.query_one("#project-list")
            list_view.index = 0
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, DashboardScreen)
            assert app.screen.project.name == "demo"

    run_async(scenario())


def test_dashboard_screen_loads_health_stats_and_doctor_data(sample_repo):
    _register("demo", sample_repo)
    project = cfgmod.load_projects()["demo"]

    async def scenario():
        app = DevtoolsApp(initial_project="demo")
        async with app.run_test() as pilot:
            # load_data() runs in a background worker; give it a moment.
            for _ in range(20):
                await pilot.pause()
                health_text = str(app.screen.query_one("#health-panel").render())
                if "Loading" not in health_text:
                    break
            assert isinstance(app.screen, DashboardScreen)
            assert app.screen.project.name == project.name
            health_text = str(app.screen.query_one("#health-panel").render())
            assert "Health:" in health_text
            stats_text = str(app.screen.query_one("#stats-panel").render())
            assert "Files:" in stats_text

    run_async(scenario())


def test_devtools_app_opens_straight_to_dashboard_with_initial_project(sample_repo):
    _register("demo", sample_repo)

    async def scenario():
        app = DevtoolsApp(initial_project="demo")
        async with app.run_test() as pilot:
            await pilot.pause()
            assert isinstance(app.screen, DashboardScreen)

    run_async(scenario())


def test_devtools_app_falls_back_to_picker_for_unknown_initial_project():
    async def scenario():
        app = DevtoolsApp(initial_project="does-not-exist")
        async with app.run_test() as pilot:
            await pilot.pause()
            assert isinstance(app.screen, ProjectListScreen)

    run_async(scenario())
