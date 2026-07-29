"""`devtools watch` — file-watcher re-runs a command on change (backlog
#39, P1).

Polling-based (mtime fingerprint of the scanned file set) rather than a
real OS-level file-watcher (`watchdog`/inotify): no new dependency, works
identically on every platform, and is trivially deterministic to test
(inject a fake clock/sleep and bound the iteration count) -- consistent
with the project's existing "good enough signal, not a perfect one"
philosophy (`is_probably_binary`, `find_duplicate_files`'s exact-hash
comparison, `hotspots`' churn x complexity score). A 1-2 second poll
interval is imperceptible for an interactive watch loop; it's not trying
to be a low-latency build-system watcher.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

from devtools.core.ignore_rules import IgnoreRules
from devtools.core.scanner import scan_project

Fingerprint = dict[str, float]
OnChange = Callable[[bool], None]  # arg: True on the initial run, False on every re-run after a change


def compute_fingerprint(root: Path, ignore_rules: IgnoreRules) -> Fingerprint:
    """rel_path -> mtime for every file `scan_project` would see. Cheap
    enough to recompute every poll for typical project sizes; parallel
    scanning is skipped here since the win from threading doesn't clear
    the overhead at this scan frequency."""
    return {entry.rel_path: entry.mtime for entry in scan_project(root, ignore_rules, parallel=False)}


def watch_loop(
    root: Path,
    ignore_rules: IgnoreRules,
    on_change: OnChange,
    poll_interval: float = 2.0,
    max_iterations: int | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> int:
    """Runs `on_change(True)` immediately, then polls every `poll_interval`
    seconds and calls `on_change(False)` whenever the fingerprint differs
    from the last one observed. Returns the number of times `on_change`
    fired (including the initial run) -- mainly useful for tests.

    `max_iterations=None` polls forever (real CLI usage, exited via
    Ctrl+C/KeyboardInterrupt from the caller); a finite value makes the
    loop deterministic for tests without needing to fake real time.
    """
    fingerprint = compute_fingerprint(root, ignore_rules)
    on_change(True)
    fire_count = 1

    iterations = 0
    while max_iterations is None or iterations < max_iterations:
        sleep_fn(poll_interval)
        new_fingerprint = compute_fingerprint(root, ignore_rules)
        if new_fingerprint != fingerprint:
            fingerprint = new_fingerprint
            on_change(False)
            fire_count += 1
        iterations += 1

    return fire_count
