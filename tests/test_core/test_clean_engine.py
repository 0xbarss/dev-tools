from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone

from devtools.core.clean_engine import filter_older_than, find_candidates, total_size


def test_find_candidates_detects_pycache_and_node_modules(sample_repo):
    candidates = find_candidates(sample_repo)
    rel_paths = {c.rel_path for c in candidates}
    assert "__pycache__" in rel_paths
    assert "node_modules" in rel_paths


def test_total_size_sums_candidate_sizes(sample_repo):
    candidates = find_candidates(sample_repo)
    assert total_size(candidates) >= 0
    assert total_size(candidates) == sum(c.size for c in candidates)


def test_filter_older_than_excludes_recent_files(sample_repo):
    candidates = find_candidates(sample_repo)
    future_cutoff = datetime.now(timezone.utc) + timedelta(days=1)
    assert filter_older_than(candidates, future_cutoff) == candidates

    past_cutoff = datetime.now(timezone.utc) - timedelta(days=365)
    assert filter_older_than(candidates, past_cutoff) == []


def test_filter_older_than_includes_aged_files(sample_repo):
    pyc = sample_repo / "old_module.pyc"
    pyc.write_bytes(b"0")
    old_time = time.time() - 40 * 86400
    os.utime(pyc, (old_time, old_time))

    candidates = find_candidates(sample_repo)
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    old = filter_older_than(candidates, cutoff)
    assert any(c.rel_path == "old_module.pyc" for c in old)