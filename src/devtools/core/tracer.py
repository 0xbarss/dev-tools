"""Per-phase timing for slow commands (`devtools <cmd> --trace`,
Prioritized Backlog: "Profiling", P3).

`history_log.py` already records total wall-clock time per invocation
(spec §11); this gives commands a cheap way to break that total down into
named phases ("scan", "read", "render", ...) when `--trace` is passed,
without adding a real profiler dependency. Commands that don't care about
tracing never touch this module -- `Tracer.phase()` is a no-op-cheap context
manager either way, so instrumenting a command costs nothing when tracing
is off.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass, field


@dataclass
class PhaseTiming:
    name: str
    seconds: float


class Tracer:
    """Collects named phase durations for a single command invocation.

    `enabled=False` (the default) makes every `phase()` call a near-free
    no-op -- so `_shared.py`/commands can unconditionally wrap sections in
    `state.tracer.phase(...)` and only pay for it when `--trace` is set.
    """

    def __init__(self, enabled: bool = False) -> None:
        self.enabled = enabled
        self.timings: list[PhaseTiming] = []

    @contextmanager
    def phase(self, name: str):
        if not self.enabled:
            yield
            return
        start = time.perf_counter()
        try:
            yield
        finally:
            self.timings.append(PhaseTiming(name=name, seconds=time.perf_counter() - start))

    @property
    def total_seconds(self) -> float:
        return sum(t.seconds for t in self.timings)

    def as_rows(self) -> list[dict]:
        """Rows suitable for `output.render_table`, sorted slowest-first,
        with each phase's share of the traced total."""
        total = self.total_seconds
        rows = []
        for t in sorted(self.timings, key=lambda t: t.seconds, reverse=True):
            pct = (t.seconds / total * 100) if total else 0.0
            rows.append({"phase": t.name, "seconds": f"{t.seconds:.3f}", "pct": f"{pct:.1f}%"})
        return rows
