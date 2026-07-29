"""`devtools stats --hotspots` — churn x complexity ranking (backlog #10,
P1). "Hotspots" are files that are both frequently changed (churn, via git
log) and complex (cyclomatic complexity for Python; line count as a proxy
for other languages, since `complexity_engine` is Python-only today) --
the files most worth a refactor or extra test coverage, since bugs
cluster where change frequency and complexity overlap.

Score is deliberately simple (churn * complexity) rather than a fitted
model: it's explainable in one sentence, which matters more here than a
marginally "better" weighting nobody can reason about.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from devtools.core.complexity_engine import compute_complexity
from devtools.core.ignore_rules import IgnoreRules
from devtools.core.stats_engine import compute_stats
from devtools.utils import git as gitmod

DEFAULT_SINCE = "180 days ago"


@dataclass
class Hotspot:
    rel_path: str
    churn: int
    complexity: int
    complexity_is_estimated: bool  # True when falling back to line-count (non-Python files)
    score: int


def compute_hotspots(
    root: Path,
    ignore_rules: IgnoreRules,
    since: str = DEFAULT_SINCE,
    top: int = 20,
) -> list[Hotspot]:
    if not gitmod.is_git_repo(root):
        raise gitmod.GitError(f"{root} is not a git repository")

    churn = gitmod.file_commit_counts(root, since=since)
    stats = compute_stats(root, ignore_rules, count_tokens_flag=False)

    complexity_by_file: dict[str, int] = {}
    for file_result in compute_complexity(root, ignore_rules):
        complexity_by_file[file_result.rel_path] = sum(fn.complexity for fn in file_result.functions)

    hotspots: list[Hotspot] = []
    for fs in stats.all_files:
        commits = churn.get(fs.rel_path, 0)
        if commits == 0:
            continue  # untouched in the window -> not a hotspot, regardless of complexity
        if fs.rel_path in complexity_by_file:
            complexity = complexity_by_file[fs.rel_path]
            estimated = False
        else:
            complexity = fs.lines
            estimated = True
        # A file with zero measured complexity (e.g. a Python file with no
        # functions, just module-level code) would otherwise always score
        # 0 and never surface, even if it churns constantly -- floor it at
        # 1 so churn alone can still make something visible.
        complexity = max(complexity, 1)
        hotspots.append(
            Hotspot(
                rel_path=fs.rel_path,
                churn=commits,
                complexity=complexity,
                complexity_is_estimated=estimated,
                score=commits * complexity,
            )
        )

    hotspots.sort(key=lambda h: h.score, reverse=True)
    return hotspots[:top]