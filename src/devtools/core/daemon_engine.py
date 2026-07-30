"""`devtools daemon` — run `devtools watch` detached in the background
(backlog #51, P3). Deliberately a thin wrapper around the existing
`watch` command rather than a new watching implementation: `daemon start`
launches `python -m devtools.cli watch ...` as a detached subprocess,
redirects its output to a log file, and remembers its pid; `stop`/
`status` just manage that pid. One daemon per project name (a second
`start` for the same project without `stop`ing first is refused).
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from devtools.utils.paths import daemon_log_file_path, daemon_pid_file_path


class DaemonError(RuntimeError):
    pass


@dataclass
class DaemonStatus:
    project: str
    running: bool
    pid: int | None = None
    started_at: float | None = None
    log_path: Path | None = None


def _is_pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    except ProcessLookupError:
        return False
    return True


def _read_pid(project: str) -> int | None:
    pid_file = daemon_pid_file_path(project)
    if not pid_file.is_file():
        return None
    try:
        return int(pid_file.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        return None


def status(project: str) -> DaemonStatus:
    pid = _read_pid(project)
    if pid is None or not _is_pid_alive(pid):
        return DaemonStatus(project=project, running=False)
    pid_file = daemon_pid_file_path(project)
    started_at = pid_file.stat().st_mtime if pid_file.is_file() else None
    return DaemonStatus(project=project, running=True, pid=pid, started_at=started_at, log_path=daemon_log_file_path(project))


def start(project: str, root: Path, command: str, interval: float = 5.0, extra_args: list[str] | None = None) -> DaemonStatus:
    existing = status(project)
    if existing.running:
        raise DaemonError(f"A daemon is already running for '{project}' (pid {existing.pid}). Stop it first with `devtools daemon stop {project}`.")

    pid_file = daemon_pid_file_path(project)
    log_file = daemon_log_file_path(project)
    pid_file.parent.mkdir(parents=True, exist_ok=True)

    cmd = [sys.executable, "-m", "devtools.cli", "watch", command, project, "--interval", str(interval), *(extra_args or [])]
    with open(log_file, "ab") as log_fh:
        # start_new_session detaches the child from this process's controlling
        # terminal/session, so it survives after this CLI invocation exits.
        proc = subprocess.Popen(
            cmd,
            cwd=root,
            stdout=log_fh,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    pid_file.write_text(str(proc.pid), encoding="utf-8")
    return DaemonStatus(project=project, running=True, pid=proc.pid, started_at=time.time(), log_path=log_file)


def stop(project: str, timeout: float = 5.0) -> bool:
    """Returns False if no daemon was running for `project`."""
    current = status(project)
    if not current.running or current.pid is None:
        daemon_pid_file_path(project).unlink(missing_ok=True)
        return False

    import signal

    os.kill(current.pid, signal.SIGTERM)
    deadline = time.time() + timeout
    while time.time() < deadline and _is_pid_alive(current.pid):
        time.sleep(0.1)
    if _is_pid_alive(current.pid):
        os.kill(current.pid, signal.SIGKILL)
    daemon_pid_file_path(project).unlink(missing_ok=True)
    return True


def tail_log(project: str, lines: int = 20) -> list[str]:
    log_path = daemon_log_file_path(project)
    if not log_path.is_file():
        return []
    content = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    return content[-lines:]
