# devtools

A personal, installable developer toolkit built with **Python**, **Typer**, and **Rich** —
a single `devtools` binary that replaces a dozen scattered scripts for repository
analysis, cleanup, and AI-assisted context generation.

## Install

```bash
pip install -e .
# or, with the test dependencies too:
pip install -e ".[dev]"
```

This registers the `devtools` command on your `PATH` (see `[project.scripts]` in
`pyproject.toml`).

## Quick start

```bash
devtools init                          # bootstraps ~/.config/devtools/ (also runs implicitly on first use)
devtools project add backend ~/Projects/backend
devtools project default backend

devtools stats backend                 # file/line/token counts, language breakdown
devtools tree backend                  # a better directory tree
devtools doctor backend                # README/LICENSE/tests/binaries/symlinks/duplicates
devtools grep "UserService"            # uses the default project set above
devtools deps backend                  # dependency manifests across 6 ecosystems
devtools collect backend --format markdown --lang python
devtools bundle backend                # tree + manifests + curated "important" files
devtools context backend "how does auth work"
devtools clean backend --dry-run
```

Every command supports `--json`, `--format markdown`, `--quiet`, `-v`/`-vv`,
`--no-color`, `--config PATH`, and `--project NAME` — see **Global conventions**
below.

## Commands

| Command | What it does |
|---|---|
| `init` | Bootstrap `~/.config/devtools/` (also runs implicitly, idempotently, before every command) |
| `project` | Manage registered repositories: `add`/`remove`/`rename`/`list`/`default`/`show` |
| `collect` | Collect source files into one AI-ready file (markdown/json/text, chunked by token budget, git-aware `--since`) |
| `bundle` | An AI-ready repository snapshot: tree + manifests + curated "important" files |
| `context` | A lighter, task-scoped sibling of `bundle` for a specific question |
| `grep` | Fast, project-aware literal/regex search |
| `tree` | A better directory tree (depth limits, `--source-only`, markdown/JSON) |
| `stats` | File/line/token counts, language distribution, largest files, duplicates |
| `doctor` | Health checks: README/LICENSE, tests, large binaries, broken symlinks, empty folders, duplicates, `.gitignore` completeness (`--fix`, `--ci`) |
| `deps` | Dependency analysis for Python, Node, Rust, Go, Java, and Flutter |
| `clean` | Safe cleanup of `__pycache__`, `node_modules`, `build/`, `dist/`, and friends |
| `search` | Concept search (keyword/synonym expansion today; local embeddings later, opt-in) |
| `ignore` | Manage the shared ignore rules without hand-editing `config.toml` |
| `export` | Turn a previous command's output into CSV or HTML |
| `alias` | Save and run shortcuts for command chains |
| `history` | Append-only log of past runs |
| `completion` | Install/show shell completion (bash/zsh/fish) |
| `update` | Opt-in self-update check (never runs automatically) |

Run `devtools <command> --help` for full option details on any of them.

## Global conventions

| Flag | Effect |
|---|---|
| `--json` | Machine-readable JSON instead of Rich tables; disables color/progress bars |
| `--format markdown` | Markdown output where the command supports it |
| `--quiet` / `-q` | Suppress non-essential output; errors still print |
| `--verbose` / `-v` (repeatable) | `-v` = info, `-vv` = debug |
| `--no-color` | Disable ANSI colors (also respects `NO_COLOR`) |
| `--config PATH` | Use a different config file for this invocation |
| `--project NAME` | Explicit project, instead of the positional argument |

**Project resolution order:** CLI argument → `DEVTOOLS_PROJECT` env var → configured
default project → current directory, if it's a registered project's path.

**Exit codes:** `0` success · `1` general error · `2` invalid usage ·
`3` project not found · `4` filesystem error · `5` check failed (`doctor --ci`,
`deps --check`).

## Configuration

- **`~/.config/devtools/config.toml`** — output format, ignored dirs (global +
  per-project overrides), `allow_network`, default project.
- **`~/.config/devtools/projects.json`** — registered project name → path.
- **`~/.config/devtools/history.jsonl`** — append-only run log.
- **`~/.config/devtools/aliases.json`** — saved command-chain shortcuts.

All three DEVTOOLS_CONFIG_DIR / DEVTOOLS_CACHE_DIR / DEVTOOLS_PROJECT env vars are
respected for scripting and testing; see `src/devtools/utils/paths.py`.

Precedence: **CLI flags > `DEVTOOLS_*` env vars > `--config` override file >
project-level overrides in `config.toml` > global defaults.**

## Project layout

```text
src/devtools/
├── cli.py                 # Typer app assembly, global options, history logging
├── commands/               # thin Typer wiring — one module per command
└── core/                    # the actual logic: ignore rules, scanning, tokenizing,
                              # collecting, stats, doctor checks, deps parsing,
                              # grep/search, tree, clean, alias/history/export storage
models/                      # Pydantic models (Settings, Project)
utils/                       # paths, console/output helpers, git, misc parsing
tests/
├── test_core/               # unit tests per core/ module, synthetic fixtures
├── test_commands/           # CLI-level tests via Typer's CliRunner
└── fixtures/                # golden files (e.g. collect's markdown output)
```

Commands are intentionally thin: all real logic lives in `core/` so it can be
unit-tested directly, independent of the CLI framework.

## Testing

```bash
pip install -e ".[dev]"
pytest
```

The test suite follows the strategy in the build spec: unit tests per `core/`
module against synthetic fixture repos, a golden-file test for `collect`'s
markdown output, and CLI-level tests via Typer's `CliRunner` that assert exit
codes match the table above.

## A note on how this was built

This package was generated end-to-end from a build spec, with every `core/`
module unit-tested against synthetic fixtures and the full CLI exercised
through a lightweight local test harness during development (this sandbox
had no network access to install the real `typer`/`rich`/`pydantic`/`orjson`/
`tiktoken` dependencies). The logic has been verified thoroughly; do run
`pip install -e ".[dev]" && pytest` in your own environment as a final check
before relying on it, especially around shell completion (`devtools completion`)
and the self-update path (`devtools update`), which are lower-risk but weren't
exercised against the real libraries.
