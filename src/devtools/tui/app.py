"""Screens and the top-level `App` for `devtools ui`. See `tui/__init__.py`
for the design rationale (thin layer over `core/`, same as `commands/`)."""

from __future__ import annotations

from rich.markup import escape as escape_markup
from textual import work
from textual.app import App, ComposeResult
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Label, ListItem, ListView, Static

from devtools.core import config as cfgmod
from devtools.core.doctor_checks import run_all_checks
from devtools.core.health_engine import compute_health
from devtools.core.ignore_rules import IgnoreRules
from devtools.core.stats_engine import compute_stats
from devtools.models.project import Project

_PROJECT_ITEM_PREFIX = "proj-"


class ProjectListScreen(Screen):
    """Landing screen: pick a registered project to open its dashboard."""

    BINDINGS = [("q", "quit", "Quit")]  # noqa: RUF012 - Textual's own documented convention for this attribute

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static("Select a project (Enter to open, q to quit):", id="project-list-title")
        yield ListView(id="project-list")
        yield Footer()

    def on_mount(self) -> None:
        self._populate()

    def _populate(self) -> None:
        projects = cfgmod.load_projects()
        list_view = self.query_one("#project-list", ListView)
        if not projects:
            list_view.append(
                ListItem(Label("No projects registered. Run `devtools project add <name> <path>` first, then reopen the UI."))
            )
            return
        for name, project in sorted(projects.items()):
            list_view.append(
                ListItem(Label(f"{name}  [{project.path}]", markup=False), id=f"{_PROJECT_ITEM_PREFIX}{name}")
            )

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        item_id = event.item.id
        if not item_id or not item_id.startswith(_PROJECT_ITEM_PREFIX):
            return
        name = item_id[len(_PROJECT_ITEM_PREFIX) :]
        project = cfgmod.load_projects().get(name)
        if project is not None:
            self.app.push_screen(DashboardScreen(project))


class DashboardScreen(Screen):
    """Per-project view: health score, stats summary, and doctor findings --
    each panel backed directly by the matching `core/` engine, computed in
    a background worker so a large repo doesn't freeze the UI."""

    BINDINGS = [  # noqa: RUF012 - Textual's own documented convention for this attribute
        ("escape", "app.pop_screen", "Back"),
        ("r", "refresh_data", "Refresh"),
        ("q", "quit", "Quit"),
    ]

    def __init__(self, project: Project) -> None:
        super().__init__()
        self.project = project

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static(f"[bold]{escape_markup(self.project.name)}[/bold]  --  {escape_markup(self.project.path)}", id="dash-title")
        yield Static("Loading health...", id="health-panel")
        yield Static("Loading stats...", id="stats-panel")
        yield DataTable(id="doctor-table")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#doctor-table", DataTable)
        table.add_columns("severity", "check", "message")
        self.load_data()

    def action_refresh_data(self) -> None:
        self.query_one("#health-panel", Static).update("Refreshing health...")
        self.query_one("#stats-panel", Static).update("Refreshing stats...")
        self.load_data()

    @work(thread=True, exclusive=True)
    def load_data(self) -> None:
        root = self.project.resolved_path
        settings = cfgmod.load_settings()
        ignored_dirs = settings.ignored_dirs_for(self.project.name)
        rules = IgnoreRules.build(root=root, base_ignored_dirs=ignored_dirs)

        stats = compute_stats(root, rules, top=5)
        health = compute_health(root, rules, ignored_dirs)
        issues = run_all_checks(root, rules, ignored_dirs)

        self.app.call_from_thread(self._display_results, stats, health, issues)

    def _display_results(self, stats, health, issues) -> None:
        health_panel = self.query_one("#health-panel", Static)
        health_lines = [f"[bold]Health: {health.overall_score}/100[/bold]"]
        health_lines.extend(f"  {c.name}: {c.score}/{c.weight} -- {c.summary}" for c in health.categories)
        health_panel.update("\n".join(health_lines))

        stats_panel = self.query_one("#stats-panel", Static)
        stats_panel.update(
            f"[bold]Files:[/bold] {stats.file_count}   "
            f"[bold]Lines:[/bold] {stats.total_lines}   "
            f"[bold]Tokens (est.):[/bold] {stats.total_tokens}"
        )

        table = self.query_one("#doctor-table", DataTable)
        table.clear()
        for issue in issues[:15]:
            table.add_row(issue.severity, issue.check, issue.message)


class DevtoolsApp(App):
    """The `devtools ui` application: a project picker plus a per-project
    dashboard, both driven by the same engines as the scriptable CLI."""

    CSS = """
    #health-panel, #stats-panel {
        padding: 1 2;
        border: round $accent;
        margin: 1 1 0 1;
    }
    #project-list-title {
        padding: 1 2;
    }
    """
    TITLE = "devtools"

    def __init__(self, initial_project: str | None = None) -> None:
        super().__init__()
        self.initial_project = initial_project

    def on_mount(self) -> None:
        project = cfgmod.load_projects().get(self.initial_project) if self.initial_project else None
        if project is not None:
            self.push_screen(DashboardScreen(project))
        else:
            self.push_screen(ProjectListScreen())


def run_tui(initial_project: str | None = None) -> None:
    DevtoolsApp(initial_project=initial_project).run()