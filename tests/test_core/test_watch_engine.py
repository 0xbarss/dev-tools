from __future__ import annotations

import time

from devtools.core.ignore_rules import IgnoreRules
from devtools.core.watch_engine import compute_fingerprint, watch_loop


def _rules(root):
    return IgnoreRules.build(root, base_ignored_dirs=["node_modules", "__pycache__"])


def _noop_sleep(_seconds: float) -> None:
    return None


def test_compute_fingerprint_tracks_mtimes(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n")
    fp = compute_fingerprint(tmp_path, _rules(tmp_path))
    assert "a.py" in fp
    assert isinstance(fp["a.py"], float)


def test_watch_loop_fires_once_immediately_with_no_changes(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n")
    calls = []
    fire_count = watch_loop(
        tmp_path,
        _rules(tmp_path),
        on_change=lambda initial: calls.append(initial),
        max_iterations=3,
        sleep_fn=_noop_sleep,
    )
    assert calls == [True]
    assert fire_count == 1


def test_watch_loop_fires_again_when_a_file_changes(tmp_path):
    f = tmp_path / "a.py"
    f.write_text("x = 1\n")
    calls = []
    iteration_count = 0

    def sleep_and_mutate(_seconds: float) -> None:
        nonlocal iteration_count
        iteration_count += 1
        if iteration_count == 1:
            # Ensure the mtime actually differs on filesystems with coarse
            # mtime resolution.
            time.sleep(0.01)
            f.write_text("x = 2\n")

    fire_count = watch_loop(
        tmp_path,
        _rules(tmp_path),
        on_change=lambda initial: calls.append(initial),
        max_iterations=3,
        sleep_fn=sleep_and_mutate,
    )
    assert calls == [True, False]
    assert fire_count == 2


def test_watch_loop_does_not_refire_if_nothing_changes_between_polls(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n")
    calls = []
    fire_count = watch_loop(
        tmp_path,
        _rules(tmp_path),
        on_change=lambda initial: calls.append(initial),
        max_iterations=5,
        sleep_fn=_noop_sleep,
    )
    assert calls == [True]
    assert fire_count == 1


def test_watch_loop_detects_new_file_creation(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n")
    calls = []
    iteration_count = 0

    def sleep_and_add_file(_seconds: float) -> None:
        nonlocal iteration_count
        iteration_count += 1
        if iteration_count == 1:
            (tmp_path / "b.py").write_text("y = 2\n")

    fire_count = watch_loop(
        tmp_path,
        _rules(tmp_path),
        on_change=lambda initial: calls.append(initial),
        max_iterations=2,
        sleep_fn=sleep_and_add_file,
    )
    assert calls == [True, False]
    assert fire_count == 2