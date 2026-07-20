from __future__ import annotations

from devtools.core.history_log import read_entries, record_run, run_timer


def test_record_and_read_entries(tmp_path):
    log = tmp_path / "history.jsonl"
    record_run("stats", "api", 12, 0, log)
    record_run("doctor", "api", 55, 5, log)
    record_run("stats", "blog", 8, 0, log)

    entries = read_entries(log)
    assert len(entries) == 3
    assert entries[0]["cmd"] == "stats"
    assert entries[1]["exit_code"] == 5


def test_read_entries_filters_by_project(tmp_path):
    log = tmp_path / "history.jsonl"
    record_run("stats", "api", 1, 0, log)
    record_run("stats", "blog", 1, 0, log)
    entries = read_entries(log, project="api")
    assert len(entries) == 1
    assert entries[0]["project"] == "api"


def test_read_entries_last_n(tmp_path):
    log = tmp_path / "history.jsonl"
    for i in range(5):
        record_run("stats", "api", i, 0, log)
    entries = read_entries(log, last=2)
    assert len(entries) == 2


def test_read_entries_skips_corrupted_lines(tmp_path):
    log = tmp_path / "history.jsonl"
    record_run("stats", "api", 1, 0, log)
    with log.open("a") as f:
        f.write("not valid json\n")
    record_run("doctor", "api", 2, 0, log)
    entries = read_entries(log)
    assert len(entries) == 2


def test_run_timer_measures_nonnegative_duration():
    with run_timer() as t:
        pass
    assert t.duration_ms >= 0
