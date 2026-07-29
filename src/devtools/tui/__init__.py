"""`devtools ui` — the interactive TUI (backlog #6, P1, Large).

Thin over the existing `core/` engines, mirroring the `commands/` pattern
exactly: every number shown here comes from the same `compute_stats`,
`compute_health`, and `run_all_checks` calls the scriptable CLI uses, so
the TUI and `devtools stats`/`health`/`doctor` can never quietly disagree.
"""
