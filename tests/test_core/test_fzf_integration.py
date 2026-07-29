from __future__ import annotations

from devtools.core import fzf_integration


def test_run_fzf_returns_none_when_not_installed(monkeypatch):
    monkeypatch.setattr(fzf_integration.shutil, "which", lambda name: None)
    assert fzf_integration.run_fzf(["a", "b"]) is None


def test_run_fzf_returns_none_for_empty_candidates():
    assert fzf_integration.run_fzf([]) is None


def test_fzf_available_reflects_which(monkeypatch):
    monkeypatch.setattr(fzf_integration.shutil, "which", lambda name: "/usr/bin/fzf")
    assert fzf_integration.fzf_available() is True
    monkeypatch.setattr(fzf_integration.shutil, "which", lambda name: None)
    assert fzf_integration.fzf_available() is False


def test_run_fzf_returns_selected_lines(monkeypatch):
    class FakeResult:
        returncode = 0
        stdout = "b\n"

    monkeypatch.setattr(fzf_integration.shutil, "which", lambda name: "/usr/bin/fzf")
    monkeypatch.setattr(fzf_integration.subprocess, "run", lambda *a, **k: FakeResult())
    assert fzf_integration.run_fzf(["a", "b", "c"]) == ["b"]


def test_run_fzf_returns_none_on_cancel(monkeypatch):
    class FakeResult:
        returncode = 130
        stdout = ""

    monkeypatch.setattr(fzf_integration.shutil, "which", lambda name: "/usr/bin/fzf")
    monkeypatch.setattr(fzf_integration.subprocess, "run", lambda *a, **k: FakeResult())
    assert fzf_integration.run_fzf(["a", "b"]) is None