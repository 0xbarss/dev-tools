# devtools

A personal, installable developer toolkit built with **Python**, **Typer**, and **Rich** —
a single `devtools` binary that replaces a dozen scattered scripts for repository
analysis, cleanup, git/PR workflows, and AI-assisted context generation.

Every command follows the same shape: a thin `commands/` wrapper over a real,
independently-testable `core/` engine, deterministic checks run first and for
free, AI is opt-in and layered on top (never required unless the command's
whole point is AI), and everything supports `--json` for scripting.

## Install

```bash
pip install -e .
# or, with the test dependencies too:
pip install -e ".[dev]"
# TUI (devtools ui):
pip install -e ".[tui]"
# MCP server (devtools mcp-serve):
pip install -e ".[mcp]"
# OCR (devtools ocr) -- also needs a local `tesseract` binary on PATH:
pip install -e ".[ocr]"
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
devtools health backend                # one 0-100 score rolling all of the above up
devtools grep "UserService"            # uses the default project set above
devtools deps backend                  # dependency manifests across 6 ecosystems
devtools collect backend --format markdown --lang python
devtools bundle backend                # tree + manifests + curated "important" files
devtools context backend "how does auth work"
devtools index build backend --rag && devtools ask backend "how does auth work"
devtools clean backend --dry-run
```

Every command supports `--json`, `--format markdown`, `--quiet`, `-v`/`-vv`,
`--no-color`, `--config PATH`, and `--project NAME` — see **Global conventions**
below.

## Table of contents

- [Project & configuration](#project--configuration)
- [Exploration & understanding](#exploration--understanding)
- [AI-assisted context & explanation](#ai-assisted-context--explanation)
- [Code quality & health](#code-quality--health)
- [Git & PR workflow](#git--pr-workflow)
- [Compliance, security & reporting](#compliance-security--reporting)
- [Automation & integration](#automation--integration)
- [Extensibility](#extensibility-plugins-templates-docs)
- [Personal knowledge tools](#personal-knowledge-tools)
- [Interactive TUI](#interactive-tui)
- [Global conventions](#global-conventions)
- [Configuration](#configuration)
- [Project layout](#project-layout)
- [Testing](#testing)

Every command below also answers to `devtools <command> --help` for the full,
authoritative option list — this README explains **what each command is for
and why you'd reach for it**; `--help` is the flag reference.

---

## Project & configuration

### `init`
**What:** Bootstraps `~/.config/devtools/` (`config.toml`, `projects.json`, etc.). Runs implicitly and idempotently before every other command, so you rarely need to call it yourself.
**Use it:** `devtools init`
**Why:** Nothing else works without a config directory; calling it explicitly is only useful for scripting a fresh machine setup.

### `project`
**What:** Manage the repositories devtools knows about, so later commands can take a short `name` instead of a full path.
**Use it:**
```bash
devtools project add backend ~/Projects/backend
devtools project default backend   # so bare `devtools stats` works with no name
devtools project list
devtools project list --fzf        # interactively pick one via fzf, prints its name
devtools project show backend
devtools project rename backend api
devtools project remove api
```
**Why:** Every other command's "project" argument resolves through this registry (falling back to `DEVTOOLS_PROJECT`, the default project, then the current directory) — register once, refer to it by name everywhere after. `--fzf` is for when you've registered enough projects that scanning a plain list by eye is slower than fuzzy-typing a few letters (falls back to the normal list if `fzf` isn't installed).

### `config`
**What:** Get/set/list values in `config.toml` (default project, ignored dirs, AI provider, output format) without hand-editing the file.
**Use it:**
```bash
devtools config set ai_provider claude
devtools config get ai_provider
devtools config list
```
**Why:** Safer than editing TOML by hand, and scriptable — e.g. a setup script can run `devtools config set ...` on a new machine.

### `ignore`
**What:** Manage the shared ignore rules (`.gitignore`-style patterns plus a base "always skip" dir list) used by every scanning command (`collect`, `bundle`, `grep`, `tree`, `stats`, `doctor`, ...).
**Use it:**
```bash
devtools ignore add "*.generated.ts"
devtools ignore list
devtools ignore remove "*.generated.ts"
```
**Why:** One ignore list instead of teaching every command its own `--exclude` flags; add a pattern once and every scanning command respects it.

There's also a second, file-level default list (`ignored_file_patterns` in `config.toml`) that every scanning command combines with the directory list above — it exists specifically to catch build/cache *files* that live outside one of the ignored *directories* (a stray `.pyc`, a checked-in `.min.js` bundle, `.DS_Store`) which directory-name pruning alone can't reach:
```bash
devtools config get ignored_file_patterns
devtools config set ignored_file_patterns "*.pyc,*.min.js,.DS_Store,..."   # replaces the whole list
```

### `index`
**What:** Builds a local, on-disk SQLite index of a project for faster repeated scans, in two independent flavors: the default whole-file index (paths/sizes/language, plus TF-IDF vectors with `--vectors` for `search --semantic`), and, with `--rag`, a separate **chunk-level** index over `collect` output (see `devtools ask`, below) — persisted, chunked, and vectorized once so repeat questions don't re-scan or re-embed the project. Both support `--full` to force a full rebuild instead of the default incremental (mtime-based) one.
**Use it:**
```bash
devtools index build backend                      # whole-file index
devtools index build backend --vectors             # + TF-IDF vectors for `search --semantic`
devtools index build backend --rag --lang python    # chunked index for `devtools ask`
devtools index status backend                        # or: --rag, for the chunk index
devtools index clear backend                          # or: --rag, before a clean rebuild
```
**Why:** Speeds up repeated operations on large repos; entirely optional — every command works fine without ever building an index. `--rag` is specifically what makes `devtools ask` cheap to run more than once against the same project.

### `completion`
**What:** Installs or prints shell completion for bash/zsh/fish.
**Use it:** `devtools completion install` (writes to your shell's rc/completions dir) or `devtools completion show zsh` (prints only)
**Why:** Tab-completing project names and flags is a lot faster than typing them out, especially with dozens of commands.

### `update`
**What:** Reinstalls devtools from a local source checkout via `uv tool install "<source>[<extras>]"`, picking up any local code changes. There's no published package/registry for devtools to check against — it's a personal, locally-developed toolkit — so this rebuilds and reinstalls from disk rather than checking a version index. **Never runs automatically.**
**Use it:**
```bash
devtools update --check              # compare the checkout's pyproject.toml version to what's installed, no install
devtools update                      # uv tool install "<update_source_path>[<update_extras>]"
devtools update --source ~/other-checkout   # one-off: use a different checkout instead of the configured default
```
**Why:** Deliberately opt-in — a CLI silently updating itself mid-workflow is a surprise nobody asked for. `update_source_path` (default `/mnt/data6/MyFiles/Projects/devtools`) and `update_extras` (default `dev,tui,mcp`) are both configurable: `devtools config set update_source_path <path>` / `devtools config set update_extras dev,tui`. Requires `allow_network = true` (dependency resolution needs it) and `uv` on PATH.

---

## Exploration & understanding

### `tree`
**What:** A directory tree that actually respects your ignore rules and supports depth limits and a source-only mode.
**Use it:** `devtools tree backend --depth 3 --source-only`
**Why:** `tree` (the unix tool) shows you `node_modules` and `__pycache__`; this shows you the repo you actually care about.

### `stats`
**What:** File/line/token counts, language distribution, and largest files. With `--hotspots`, ranks files by churn × complexity instead — the files most worth a refactor.
**Use it:** `devtools stats backend`, `devtools stats backend --hotspots`
**Why:** A fast "what does this codebase actually look like" gut-check before diving in, and `--hotspots` turns that into a prioritized refactor list instead of a guess.

### `grep`
**What:** Fast, project-aware literal/regex search that already knows which directories to skip.
**Use it:** `devtools grep "UserService" backend`
**Why:** Same job as `grep -r`/`rg`, minus re-typing your ignore list every time, and it resolves the project by name.

### `search`
**What:** Concept search — keyword/synonym expansion (e.g. "auth" also matches "login", "credential") rather than a literal string match. `--semantic` instead ranks by cosine similarity over a local TF-IDF index (build/refresh it first with `--build-index`); `--fzf` lets you pick one result interactively; `--save`/`--load` remember a project+concept(+`--semantic`) combo under a name so you don't have to retype it.
**Use it:**
```bash
devtools search backend "authentication flow"
devtools search backend "authentication flow" --build-index   # build/refresh the index once
devtools search backend "authentication flow" --semantic       # then rank by similarity
devtools search backend "authentication flow" --fzf
devtools search backend "authentication flow" --save auth-flow
devtools search --load auth-flow
```
**Why:** For "where is the thing that does X" questions where you don't know the exact identifier to `grep` for; `--semantic` is worth the one-time index build for a search you'll re-run often, and `--save`/`--load` turn a good query into a reusable shortcut.

### `deps`
**What:** Parses dependency manifests across 6 ecosystems (Python, Node, Rust, Go, Java, Flutter) into one normalized report.
**Use it:** `devtools deps backend`, `devtools deps backend --check` (exit 5 if manifests look inconsistent, e.g. lockfile out of sync)
**Why:** One command instead of remembering `pip list`/`npm ls`/`cargo tree`/etc. per ecosystem, and `--check` makes it CI-usable.

### `graph`
**What:** Draws the project's internal Python import graph as Mermaid or DOT, with fan-in ranking (which modules are depended on the most).
**Use it:** `devtools graph backend --format mermaid > graph.mmd`
**Why:** "Who actually depends on whom" as a diagram beats inferring it from a manifest listing, especially before a refactor that touches a shared module.

### `owners`
**What:** Per-file top author and their line share, computed from `git blame`.
**Use it:** `devtools owners backend --path src/auth/`
**Why:** "Who should review this" derived from real history, not a guess or a stale CODEOWNERS file.

### `branches`
**What:** Lists local branches with last-commit age, author, and merged status; `--stale` filters to branches that look safe to delete.
**Use it:** `devtools branches backend --stale`
**Why:** A quick, evidence-based answer to "can I delete this branch" instead of squinting at `git branch -v`.

### `investigate`
**What:** A bounded, autonomous search → read → ... → finish loop over a question — for when a one-shot `explain`/`context` isn't enough because the answer spans several files you'd need to chase down yourself.
**Use it:** `devtools investigate backend "why does the checkout flow retry twice"`
**Why:** Turns "grep around for twenty minutes" into one command, with a capped number of steps so it can't run away.

---

## AI-assisted context & explanation

*(These need an AI provider configured — `devtools config set ai_provider claude|openai|ollama` plus the matching API key env var, or a local Ollama — except `collect`/`bundle`/`context` without `--compress`, which just format files for you to paste elsewhere. `ask` additionally needs its RAG index built first: `devtools index build --rag`.)*

### `collect`
**What:** Collects source files into one (or several, token-budget-chunked) AI-ready file — markdown, JSON, or plain text — with git-aware `--since` filtering. Automatically skips build/cache junk: whole directories like `node_modules`/`build`/`dist`/`__pycache__` (via `ignored_dirs`), *and* stray build-artifact files that live outside one of those directories — a `.pyc` sitting next to its `.py`, a checked-in `.min.js` bundle, a `.DS_Store` (via the new `ignored_file_patterns`, see **Configuration** below).
**Use it:** `devtools collect backend --format markdown --lang python --since main`
**Why:** The raw material every other AI-assisted command builds on, and useful on its own for pasting a repo slice into any chat-based LLM — and you don't want the token budget spent on a compiled `.class` file or a minified bundle nobody's going to read.

### `expand`
**What:** The inverse of `collect`: parses a file `collect` previously produced (markdown, json, or text — format auto-detected) and writes every file back out to a real directory on disk, recreating a working project from it. Refuses to silently overwrite a file that already exists with different content unless you pass `--force`; auto-registers the result as a project (like `new` does), so the next command can be `devtools doctor <name>`.
**Use it:**
```bash
devtools collect backend --out /tmp
devtools expand /tmp/backend_collect.md ~/Projects/backend-restored
devtools expand /tmp/backend_collect.md ~/Projects/backend-restored --force   # overwrite conflicts
```
**Why:** For turning a `collect` dump — one someone pasted into a chat, emailed you, or you generated yourself as a portable snapshot — back into an actual, working repository, instead of manually copy-pasting each file block out by hand.

### `bundle`
**What:** Produces `<project>_bundle.md`: directory tree + dependency manifests + a curated set of "important" source files (entry points, configs, core modules).
**Use it:** `devtools bundle backend`
**Why:** A single file that gives an LLM (or a new teammate) real orientation in a repo, without collecting the entire codebase.

### `context`
**What:** A lighter, task-scoped sibling of `bundle`: relevance-searches for files matching a question (or an explicit `--symbol`/`--files` glob) and formats just those. `--max-tokens` caps the budget; `--compress` (backlog #30) AI-summarizes the overflow into a compact appendix instead of silently dropping it.
**Use it:**
```bash
devtools context backend "how does auth work"
devtools context backend "how does auth work" --max-tokens 4000 --compress
```
**Why:** Most questions only need a handful of files, not the whole repo — smaller context means a cheaper, more focused LLM call, and `--compress` means a tight budget doesn't mean losing information outright.

### `explain`
**What:** One-shot AI explanation of a file or symbol, using the same relevance search `context` uses to gather the right code first.
**Use it:** `devtools explain backend src/auth/login.py`
**Why:** "What does this file do and why" in plain English, without you having to assemble the context yourself first.

### `summarize`
**What:** Drafts an ARCHITECTURE.md-style overview via a **map-reduce** pass over the whole repo: each token-budget chunk is summarized individually, then all the chunk summaries are synthesized into one coherent overview.
**Use it:** `devtools summarize backend --repo`
**Why:** For repos too large for a single LLM context window — map-reduce means you still get one coherent answer instead of hitting a context-limit error.

### `ask`
**What:** Retrieval-augmented Q&A over a **persistent, pre-built chunk index** (`devtools index build --rag`) — unlike `context`/`explain`, which relevance-search the live filesystem on every call, `ask` only ever reads from the already-chunked, already-vectorized SQLite index, so a second (or hundredth) question against the same project is cheap and doesn't touch the filesystem beyond the index file itself. Answers cite the specific file(s) and line range(s) the retrieved chunks came from.
**Use it:**
```bash
devtools index build backend --rag     # once, and again after a significant change
devtools ask backend "how does the retry logic work"
devtools ask backend "how does the retry logic work" --top 10
```
**Why:** For a project you're going to ask several questions about in one sitting — `context`/`explain` re-derive relevance from scratch every time, `ask` derives it once at build time and reuses it. If the index hasn't been built yet (or nothing in it matches), it says so and tells you the exact command to run, instead of silently falling back to a full re-scan.


---

## Code quality & health

### `doctor`
**What:** Repository hygiene checks: missing README/LICENSE/tests, large tracked binaries, broken symlinks, empty folders, duplicate files, incomplete `.gitignore`.
**Use it:** `devtools doctor backend`, `devtools doctor backend --fix` (stubs out what it safely can), `devtools doctor backend --ci` (exit 5 on any error-severity finding)
**Why:** The "did we forget something basic" check you'd otherwise only notice when a new contributor hits it.

### `health`
**What:** Rolls up `doctor` + `lint` + `complexity` + `duplication` findings into a single 0–100 score with a letter grade. `--external-report` (backlog #46) folds in an imported SARIF/SAST report as a fifth category, rebalancing the weights so the total still sums to 100.
**Use it:** `devtools health backend`, `devtools health backend --ci --min-score 70`, `devtools health backend --external-report semgrep.sarif`
**Why:** One number to track over time ("is this repo trending healthy") instead of four separate reports you have to mentally combine yourself — and a natural place for an external scanner's results to live alongside everything else, instead of a separate dashboard nobody checks.

### `lint`
**What:** Auto-detects which ecosystems are present and runs the right linter for each (shelling out to tools you already have installed), merging everything into one normalized table.
**Use it:** `devtools lint backend`, `devtools lint backend --export sarif > results.sarif`
**Why:** One command and one output shape regardless of whether the repo is Python, JS, or both — and SARIF export means it plugs straight into GitHub code scanning.

### `complexity`
**What:** Per-function cyclomatic complexity for Python, ranked highest-first.
**Use it:** `devtools complexity backend --top 10`
**Why:** Points at the specific functions most likely to be hiding bugs or resisting a clean refactor — a target list, not just a vague "this file feels big."

### `dupes`
**What:** Finds duplicate files (exact content match) or, with `--code`, near-duplicate code blocks worth extracting into a shared function.
**Use it:** `devtools dupes backend --code --min-lines 5`
**Why:** Copy-pasted code is a maintenance tax; this finds it automatically instead of relying on someone noticing during review.

### `deadcode`
**What:** Finds unused imports and unused module-level functions/classes (Python only), advisory — it flags candidates, it doesn't delete anything.
**Use it:** `devtools deadcode backend`
**Why:** Safer, faster than manually chasing down "is this still used anywhere" before deleting something.

### `clean`
**What:** Removes build/cache junk — `__pycache__`, `node_modules`, `build/`, `dist/`, and similar — safely, with a dry-run mode.
**Use it:** `devtools clean backend --dry-run` then `devtools clean backend`
**Why:** Reclaims disk space and gives you a clean tree for `collect`/`bundle` without accidentally deleting something that matters (dry-run first, always).

### `sonar-import`
**What:** Imports an external SAST report — real SARIF (CodeQL, most Semgrep/Sonar exporters, etc.) or a tiny generic `{"tool", "issues": [...]}` JSON shape — parses it, and prints a summary.
**Use it:** `devtools sonar-import backend semgrep-results.sarif`
**Why:** View what an external scanner found on its own, or combine with `devtools health --external-report <path>` to fold those findings into the same 0–100 score as everything else devtools already tracks — one health signal instead of two dashboards.

---

## Git & PR workflow

### `changelog`
**What:** Groups commits since `--since` by Conventional Commit type into a Keep-a-Changelog-style Markdown document.
**Use it:** `devtools changelog backend --since v1.2.0`
**Why:** Writing a changelog by hand from `git log` is tedious and error-prone; this reads the commit history you already have.

### `commit-lint`
**What:** Checks that every commit subject in a range follows Conventional Commits (`type(scope): description`) — known type, lowercase description, no trailing period, reasonable length. Merge commits are exempt.
**Use it:** `devtools commit-lint backend --since main`, `devtools commit-lint backend --range main..HEAD --ci`
**Why:** Enforces the same convention `changelog` already assumes commits follow, so both work together — catch a bad commit message in CI before it lands, not after `changelog` produces a garbled entry for it.

### `contributors`
**What:** Commit and line-change counts per author over a range, most active first.
**Use it:** `devtools contributors backend --since "90 days ago"`
**Why:** "Who's been active here lately" for onboarding, review-assignment, or just understanding a repo's history at a glance.

### `pr describe`
**What:** Drafts a PR description from the diff since `--since`: a summary grouped by Conventional Commit type, the changed-file list with line counts, and any referenced issues — all deterministic, **no AI configuration required**.
**Use it:** `devtools pr describe backend --since main`
**Why:** A real starting draft in the time it takes to run one command, and it still works with zero AI setup since it's built from data devtools already computes elsewhere (`changelog`'s classifier, `pr link-issues`).

### `pr link-issues`
**What:** Scans commit messages since some ref for issue references (`#123`, `PROJ-123`, `fixes #123`) and reports them, optionally as clickable links against a configured issue tracker.
**Use it:** `devtools pr link-issues backend --since main`
**Why:** Confirms your commits actually reference the issues they're meant to close, before you open the PR.

### `review`
**What:** Collects the diff since `--since` and produces a structured, AI-assisted review (bugs, style, missing tests) framed as suggestions, not blockers. `--security` layers in a **deterministic, pattern-based security scan** (hardcoded secrets, `eval`/`pickle.load`, disabled TLS verification, SQL built by string formatting, ...) that only looks at lines the diff *adds* — it runs with or without AI configured, and when AI is available it's told not to repeat what the pattern scan already caught.
**Use it:** `devtools review backend --since main`, `devtools review backend --security --since main`
**Why:** A second pair of eyes on your own diff before opening the PR — and `--security` gives you a same-day-usable security check that doesn't depend on any AI provider being set up, plus deeper AI commentary layered on top when it is.

### `commit explain`
**What:** Explains one commit's patch in plain English: what changed, why it likely changed, and anything worth double-checking.
**Use it:** `devtools commit explain backend HEAD~3`
**Why:** For "why did we do this" moments months later — faster than reading the raw diff and guessing at intent, especially for a commit with a terse message.

### `snapshot`
**What:** Saves/restores a lightweight workspace session — the current git branch, a list of files you named as relevant, and a free-form note — under a name you choose. Restoring only *shows* that information by default; `--checkout` is opt-in if you also want the branch checked out.
**Use it:**
```bash
devtools snapshot save mid-refactor --file src/auth.py --file src/session.py --note "half done extracting session logic"
devtools snapshot list
devtools snapshot restore mid-refactor
```
**Why:** Context-switching between tasks loses your mental state; this is a two-second way to write it down and get it back, without needing editor integration or any automation that could surprise you mid-task.

---

## Compliance, security & reporting

### `compliance report`
**What:** An audit-ready rollup combining hygiene (`doctor`), dependency licensing, and dead-code signals into one 0–100 score, exportable as Markdown/HTML/JSON.
**Use it:** `devtools compliance report backend --format html > compliance.html`
**Why:** The kind of report a security/compliance review actually asks for, generated from signals devtools already computes rather than assembled by hand.

### `license-check`
**What:** Best-effort dependency license report using only locally-available package metadata (no network calls).
**Use it:** `devtools license-check backend`
**Why:** Catches an incompatible license (e.g. GPL in a codebase that can't use it) before it becomes a legal problem instead of after.

### `sbom`
**What:** Generates a CycloneDX-shaped software bill of materials from detected dependency manifests.
**Use it:** `devtools sbom backend --output sbom.json`
**Why:** Increasingly a hard requirement from customers/regulators; this produces it directly from manifests you already have, in the standard shape.

---

## Automation & integration

### `ci`
**What:** Scaffolds ready-made CI pipeline config for a provider.
**Use it:** `devtools ci init backend --provider github`
**Why:** A working `doctor --ci` / `health --ci` / `lint` pipeline in one command instead of hand-writing YAML from scratch.

### `watch`
**What:** Re-runs `devtools <command> <project>` every time a tracked file changes (polling-based). `--once` runs once and exits.
**Use it:** `devtools watch doctor backend`, `devtools watch lint backend --arg --fix`
**Why:** Live feedback while you clean up a repo or refactor, instead of re-running the command by hand after every edit.

### `daemon`
**What:** Runs `devtools watch` **detached in the background** — start it, close the terminal, and check on it later. One daemon per project; `stop` sends SIGTERM (then SIGKILL after a short grace period).
**Use it:**
```bash
devtools daemon start doctor backend --interval 10
devtools daemon status backend --logs 20
devtools daemon stop backend
```
**Why:** `watch` is great in a terminal you're keeping open; `daemon` is `watch` for the case where you want continuous checking without dedicating a terminal to it.

### `run`
**What:** A task-runner front-end: finds `<task>` by name across whichever of **Makefile**, **`npm`/`package.json` scripts**, and **justfile** are present, and runs it — so you don't need to remember which one this particular repo uses.
**Use it:** `devtools run backend test`, `devtools run backend --list` (see all discovered tasks)
**Why:** Every repo picks a different task runner; this is one command and one mental model regardless of which one a given repo happens to use, and it exits with the underlying task's own exit code so it still composes with `&&` or a CI step.

### `notify`
**What:** Configures and sends Slack/Teams/Jira/generic-webhook notifications, and lets other commands (`doctor`, `deps`, ...) notify on findings.
**Use it:** `devtools notify add slack-eng https://hooks.slack.com/...`, `devtools notify send slack-eng "build failed"`
**Why:** Turns a devtools finding into a message your team actually sees, instead of a report someone has to remember to go check.

### `mcp-serve`
**What:** Runs devtools as an MCP (Model Context Protocol) server, exposing `stats`/`tree`/`doctor`/`deps`/`grep`/`search`/`lint`/`context`/`explain`/`changelog` as MCP tools.
**Use it:** `devtools mcp-serve` (point Claude Code or another MCP-aware agent at it)
**Why:** Lets an AI coding agent call devtools' own read-only analysis directly instead of re-implementing (worse) versions of the same checks itself.

### `export`
**What:** Converts a previously cached command's output into CSV, HTML, or (for `lint`) SARIF.
**Use it:** `devtools export lint --format sarif > results.sarif`
**Why:** Most commands cache their last JSON output automatically; `export` turns that into a shape some other tool (a spreadsheet, GitHub code scanning, a static site) actually wants, without re-running the analysis.

### `history`
**What:** Shows an append-only log of past `devtools` invocations — command, project, timestamp, duration, exit code.
**Use it:** `devtools history --limit 20`
**Why:** "What did I run yesterday and did it pass" without digging through shell history.

### `alias`
**What:** Saves and runs shortcuts for command chains (multiple devtools commands piped/sequenced together).
**Use it:** `devtools alias add morning "doctor && health && stats"`, `devtools alias run morning`
**Why:** Turns your personal daily routine into one word instead of retyping (or shell-history-searching for) the same three commands every morning.

---

## Extensibility: plugins, templates, docs

### `plugin`
**What:** Installs/lists/removes third-party plugins (entry-point packages or single-file scripts) that register their own devtools commands.
**Use it:** `devtools plugin install ./my_check.py`, `devtools plugin list`
**Why:** Add a team- or company-specific check without forking devtools itself.

### `marketplace`
**What:** Browse/register community plugin ideas and generate a static listing page.
**Use it:** `devtools marketplace list`, `devtools marketplace generate --output listing.html`
**Why:** Discover what other people have already built as a plugin before writing your own.

### `docs generate`
**What:** Drafts a README.md — real, grounded content (from the repo's directory tree and detected dependencies) if an AI provider is configured, otherwise the same deterministic stub template `doctor --fix` uses. Never a hard failure just because AI isn't set up.
**Use it:** `devtools docs generate backend`, `devtools docs generate backend --write --force`
**Why:** Fills exactly the gap `doctor` already flags (a missing README) with something more useful than a bare stub, when you have AI configured — and still gives you a sane starting point when you don't.

### `new`
**What:** Scaffolds a new project from a small, built-in set of templates (`python-cli`, `python-lib`, `node-lib`) — deliberately minimal and dependency-free rather than a full templating engine. Registers the new project by default so the next command can be `devtools doctor <name>`.
**Use it:** `devtools new python-cli my-tool`, `devtools new python-lib my-lib --no-license`
**Why:** A working `pyproject.toml`/`package.json` + src layout + one passing test in one command, instead of copy-pasting boilerplate from an old project every time.

---

## Personal knowledge tools

### `prompt`
**What:** A library of reusable AI prompt templates you can save once and run against any project.
**Use it:** `devtools prompt add security-review "Review this diff for security issues: {diff}"`, `devtools prompt run security-review backend`
**Why:** Stops you from re-writing (or hunting for) the same good prompt every time you need it.

### `snippet`
**What:** A small, global library of reusable code snippets, taggable and searchable.
**Use it:** `devtools snippet add retry "def retry(): ..." --language python --tags decorator`, `devtools snippet search retry`
**Why:** Your own personal Stack Overflow for the patterns you reuse across projects, without leaving the terminal.

### `bookmark`
**What:** Named quick-jumps to specific paths within your registered projects.
**Use it:** `devtools bookmark add auth backend src/auth/login.py`, `devtools bookmark go auth`
**Why:** For the handful of files you open constantly across projects — one short name instead of remembering (or re-navigating to) the full path every time.

### `ocr`
**What:** Extracts text from difficult screenshots — tiny UI text, blurry or heavily-compressed shots, low-contrast text, dark-mode screenshots — using local Tesseract OCR. Runs several image-preprocessing pipelines (upscale, grayscale, contrast, sharpen, denoise, threshold, invert) crossed with a few Tesseract page-segmentation modes, scores every attempt by Tesseract's own per-word confidence, and keeps the best one. Fully offline; no cloud OCR API involved.
**Use it:** `devtools ocr screenshot.png`, `devtools ocr dark_mode_shot.png --format json --out result.json`, `devtools ocr tiny_text.jpg --thorough --show-attempts`
**Formats:** `--format txt|json|csv|md|html` (`txt` default). `--out PATH` writes to a file instead of stdout. `--thorough` tries every pipeline/PSM combination instead of the quick default set. `--pipeline NAME` skips the comparison and forces one specific pipeline.
**Languages:** Defaults to `--lang eng`. Pass any installed Tesseract language code (`--lang tur`) or several joined with `+` for mixed-language text (`--lang eng+tur`). `devtools ocr --list-langs` shows what's installed; the command fails fast with an install hint (`pacman -S tesseract-data-<lang>` / `apt install tesseract-ocr-<lang>`) if you ask for one that isn't.
**Why:** A plain `tesseract` call on a bad screenshot often returns garbage or nothing; trying a handful of preprocessing variants and keeping the most confident result turns "OCR failed" into "OCR worked" for the screenshots that actually need it. *(requires `pip install "devtools[ocr]"` plus a local `tesseract` binary and language data, e.g. `apt install tesseract-ocr tesseract-ocr-eng` / `pacman -S tesseract tesseract-data-eng`)*

---

## Interactive TUI

### `ui`
**What:** Launches an interactive terminal dashboard: a project picker plus a per-project view (health score, stats summary, doctor findings) — the exact same `core/` engines the scriptable CLI uses, just explorable instead of one-shot.
**Use it:** `devtools ui` *(requires `pip install "devtools[tui]"`)*
- `r` refreshes the current project's data.
- **`:` opens a command palette** — type `stats`, `health`, `doctor`, `lint`, `dupes`, or `grep <query>` and see the result without leaving the dashboard.
- **`Enter` on a doctor finding drills into the file it refers to** (currently large-binary and broken-symlink findings record a path) — anything without a specific file shows its full message as a toast instead.
- `Escape` goes back, `q` quits.

**Why:** For exploring a repo interactively rather than running one command at a time — the palette covers the handful of read-only checks worth running ad hoc mid-review, and drill-down means a finding that names a file is one keystroke from actually looking at it.

---

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
| `--trace` | Print a per-phase timing breakdown after commands that support it |

**Project resolution order:** CLI argument → `--project` flag → `DEVTOOLS_PROJECT` env var →
configured default project → current directory, if it's a registered project's path.

**Exit codes:** `0` success · `1` general error · `2` invalid usage ·
`3` project not found · `4` filesystem error · `5` check failed (`doctor --ci`,
`deps --check`, `health --ci`, `commit-lint --ci`).

## Configuration

- **`~/.config/devtools/config.toml`** — output format, ignored dirs (global +
  per-project overrides), `allow_network`, default project, AI provider.
- **`~/.config/devtools/projects.json`** — registered project name → path.
- **`~/.config/devtools/history.jsonl`** — append-only run log.
- **`~/.config/devtools/aliases.json`** — saved command-chain shortcuts.
- **`~/.config/devtools/snapshots.json`** — saved workspace snapshots (branch/files/notes).
- **`~/.cache/devtools/daemon/`** — daemon pidfiles and per-project logs.

All of `DEVTOOLS_CONFIG_DIR` / `DEVTOOLS_CACHE_DIR` / `DEVTOOLS_DAEMON_DIR` /
`DEVTOOLS_PROJECT` are respected for scripting and testing; see
`src/devtools/utils/paths.py`.

Precedence: **CLI flags > `DEVTOOLS_*` env vars > `--config` override file >
project-level overrides in `config.toml` > global defaults.**

### AI provider setup

AI-assisted commands (`explain`, `review`, `context --compress`, `summarize`,
`commit explain`, `docs generate` for real content, `investigate`, `ask`) need
a provider configured:

```bash
devtools config set ai_provider claude   # or: openai, ollama
export ANTHROPIC_API_KEY=...             # matching env var for claude/openai;
                                          # ollama just needs a local server running
```

Commands that have a deterministic core (`review --security`, `pr describe`,
`docs generate`'s stub fallback, `commit-lint`) work fine with **no AI provider
configured at all** — AI only adds to them, it's never a hard requirement.

## Project layout

```text
src/devtools/
├── cli.py                 # Typer app assembly, global options, history logging
├── commands/               # thin Typer wiring — one module per command
├── core/                    # the actual logic: ignore rules, scanning, tokenizing,
│                             # collecting, stats, doctor checks, deps parsing,
│                             # grep/search, tree, clean, git-based engines
│                             # (contributors, commit-lint, pr, review/security,
│                             # summarize, docs, scaffold, task-runner, daemon,
│                             # sarif import), alias/history/export/snapshot storage
├── models/                   # Pydantic models (Settings, Project)
├── utils/                    # paths, console/output helpers, git, misc parsing
└── tui/                      # the `ui` command's screens (dashboard, command
                               # palette, file drill-down)

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

The test suite follows the strategy above: unit tests per `core/` module
against synthetic fixture repos, a golden-file test for `collect`'s markdown
output, and CLI-level tests via Typer's `CliRunner` that assert exit codes
match the table above.
