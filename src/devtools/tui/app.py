"""Screens and the top-level `App` for `devtools ui`. See `tui/__init__.py`
for the design rationale (thin layer over `core/`, same as `commands/`).

Two additions here, both backlog items previously listed as bundled with
`ui` but not yet built: a lightweight command palette (`:`, backlog #41)
for running a handful of read-only checks without leaving the dashboard,
and drill-down (Enter on a doctor finding, backlog #42) that opens the
referenced file when a finding has one (see `DoctorIssue.path`).
"""

from __future__ import annotations

from pathlib import Path

from rich.markup import escape as escape_markup
from textual import work
from textual.app import App, ComposeResult
from textual.containers import ScrollableContainer
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Input, Label, ListItem, ListView, Static

from devtools.core import config as cfgmod
from devtools.core.doctor_checks import DoctorIssue, run_all_checks
from devtools.core.health_engine import compute_health
from devtools.core.ignore_rules import IgnoreRules
from devtools.core.stats_engine import compute_stats
from devtools.models.project import Project

_PROJECT_ITEM_PREFIX = "proj-"
_PALETTE_COMMANDS = ["stats", "health", "doctor", "lint", "dupes", "grep <query>"]
_MAX_FILE_VIEW_LINES = 400


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
    a background worker so a large repo doesn't freeze the UI.

    `enter` on a doctor-table row drills into the referenced file when the
    finding has one (backlog #42); `:` opens a command palette for a
    handful of other read-only checks without leaving this screen (backlog #41).
    """

    BINDINGS = [  # noqa: RUF012 - Textual's own documented convention for this attribute
        ("escape", "app.pop_screen", "Back"),
        ("r", "refresh_data", "Refresh"),
        (":", "open_palette", "Command palette"),
        ("q", "quit", "Quit"),
    ]

    def __init__(self, project: Project) -> None:
        super().__init__()
        self.project = project
        self.issues: list[DoctorIssue] = []

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
        table.cursor_type = "row"
        self.load_data()

    def action_refresh_data(self) -> None:
        self.query_one("#health-panel", Static).update("Refreshing health...")
        self.query_one("#stats-panel", Static).update("Refreshing stats...")
        self.load_data()

    def action_open_palette(self) -> None:
        self.app.push_screen(CommandPaletteScreen(self.project))

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Drill-down (backlog #42): Enter on a finding opens its file if
        the check recorded one (`DoctorIssue.path`), otherwise shows the
        full message as a toast -- most findings (missing README, empty
        folders without a clear single file) don't have one file to jump to."""
        if event.data_table.id != "doctor-table":
            return
        index = event.cursor_row
        if index is None or index >= len(self.issues):
            return
        issue = self.issues[index]
        if issue.path:
            self.app.push_screen(FileViewScreen(self.project.resolved_path, issue.path))
        else:
            self.notify(issue.message, title=issue.check, timeout=8)

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
        self.issues = issues

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


class FileViewScreen(Screen):
    """Drill-down target (backlog #42): a read-only view of one file,
    reached from a doctor finding that references a specific path
    (currently `large_binary` and `broken_symlink`)."""

    BINDINGS = [("escape", "app.pop_screen", "Back")]  # noqa: RUF012

    def __init__(self, root: Path, rel_path: str) -> None:
        super().__init__()
        self.root = root
        self.rel_path = rel_path

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(f"[bold]{escape_markup(self.rel_path)}[/bold]", id="file-view-title")
        yield ScrollableContainer(Static("Loading...", id="file-view-content"))
        yield Footer()

    def on_mount(self) -> None:
        self.load_file()

    @work(thread=True, exclusive=True)
    def load_file(self) -> None:
        from devtools.core.filesystem import read_text_safely

        full_path = self.root / self.rel_path
        text = read_text_safely(full_path, max_bytes=200_000)
        if text is None:
            content = "(binary file, broken symlink, or otherwise unreadable -- that's likely why doctor flagged it)"
        else:
            lines = text.splitlines()
            shown = lines[:_MAX_FILE_VIEW_LINES]
            content = "\n".join(shown)
            if len(lines) > _MAX_FILE_VIEW_LINES:
                content += f"\n... ({len(lines) - _MAX_FILE_VIEW_LINES} more line(s), truncated)"
        self.app.call_from_thread(self._display, content)

    def _display(self, content: str) -> None:
        self.query_one("#file-view-content", Static).update(escape_markup(content))


class CommandPaletteScreen(Screen):
    """Lightweight command palette (backlog #41): type one of a small set
    of known command names (optionally with an argument, e.g. `grep foo`)
    and see the result without leaving the dashboard. Deliberately a fixed
    vocabulary rather than a full devtools-command interpreter -- these are
    the read-only checks that make sense to run ad hoc mid-review."""

    BINDINGS = [("escape", "app.pop_screen", "Close")]  # noqa: RUF012

    def __init__(self, project: Project) -> None:
        super().__init__()
        self.project = project

    def compose(self) -> ComposeResult:
        yield Static(f"Commands: {', '.join(_PALETTE_COMMANDS)}  (Esc to close)", id="palette-hint")
        yield Input(placeholder="e.g. stats, health, doctor, grep <query>", id="palette-input")
        yield ScrollableContainer(Static("", id="palette-result"))
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#palette-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.query_one("#palette-result", Static).update("Running...")
        self.run_command(event.value.strip())

    @work(thread=True, exclusive=True)
    def run_command(self, raw: str) -> None:
        name, _, arg = raw.partition(" ")
        name = name.strip().lower()
        arg = arg.strip()
        root = self.project.resolved_path
        settings = cfgmod.load_settings()
        ignored_dirs = settings.ignored_dirs_for(self.project.name)
        rules = IgnoreRules.build(root=root, base_ignored_dirs=ignored_dirs)

        try:
            if name == "stats":
                stats = compute_stats(root, rules, top=10)
                text = f"Files: {stats.file_count}\nLines: {stats.total_lines}\nTokens (est.): {stats.total_tokens}"
            elif name == "health":
                health = compute_health(root, rules, ignored_dirs)
                text = f"Overall: {health.overall_score}/100\n" + "\n".join(
                    f"  {c.name}: {c.score}/{c.weight} -- {c.summary}" for c in health.categories
                )
            elif name == "doctor":
                issues = run_all_checks(root, rules, ignored_dirs)
                text = "\n".join(f"[{i.severity}] {i.check}: {i.message}" for i in issues[:25]) or "No issues found."
            elif name == "lint":
                from devtools.core.lint_engine import run_lint

                report = run_lint(root)
                text = "\n".join(f"[{f.severity}] {f.file}:{f.line} ({f.rule}) {f.message}" for f in report.findings[:25]) or "No lint findings."
            elif name == "dupes":
                from devtools.core.dupes_engine import find_code_duplicates

                groups = find_code_duplicates(root, rules)
                text = "\n".join(f"{g.lines} line(s) x{len(g.occurrences)}: {', '.join(o.rel_path for o in g.occurrences)}" for g in groups[:15]) or "No duplicate blocks found."
            elif name == "grep":
                if not arg:
                    text = "Usage: grep <query>"
                else:
                    from devtools.core.search_engine import search

                    hits = search(root, rules, arg)
                    text = "\n".join(f"{h.rel_path} (score {h.score:.1f})" for h in hits[:20]) or "No matches."
            elif not name:
                text = ""
            else:
                text = f"Unknown command '{name}'. Try: {', '.join(_PALETTE_COMMANDS)}"
        except Exception as exc:  # noqa: BLE001 - surface it in the palette rather than crashing the TUI
            text = f"Error running '{name}': {exc}"

        self.app.call_from_thread(self._show_result, text)

    def _show_result(self, text: str) -> None:
        self.query_one("#palette-result", Static).update(escape_markup(text))


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
    #palette-hint {
        padding: 1 2;
        color: $text-muted;
    }
    #palette-result, #file-view-content {
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
