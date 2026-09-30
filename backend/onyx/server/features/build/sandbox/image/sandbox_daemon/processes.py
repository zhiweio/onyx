"""Background-process management for the sandbox daemon.

Owns the lifecycle of long-running processes started inside the pod: start
(``setsid`` so the process outlives any single request), append-only output
logs, byte-cursor reads, stdin, TERM→KILL stop, and listing. Metadata lives
in per-process JSON files under the process root so state survives daemon
restarts (the processes themselves die with the pod — that is the contract,
mirroring QM's process registry).

Security model: the manager never interprets the command — the caller is
the in-pod agent (via the daemon's authenticated endpoints). The log and
metadata files are the only durable state; stdin requires a live pipe, so
it is unavailable after a daemon restart (status stays readable).
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import time
from pathlib import Path
from uuid import uuid4

PROCESS_ROOT = Path("/var/lib/onyx-processes")

# Live handles: stdin pipes held by this daemon generation. Cleared on
# daemon restart — status/poll/stop keep working off the log + pid, but
# stdin is only available while the original spawner lives.
_LIVE_POPEN: dict[str, subprocess.Popen] = {}
LOG_NAME = "output.log"
META_NAME = "meta.json"
_STOP_GRACE_SECONDS = 2.0

VALID_KINDS = ("build", "dev-server", "background")


class ProcessError(RuntimeError):
    pass


class ProcessGoneError(ProcessError):
    """The pid is no longer alive and cannot be signaled or fed."""


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


_SIGNALS = {
    "TERM": signal.SIGTERM,
    "KILL": signal.SIGKILL,
    "INT": signal.SIGINT,
    "HUP": signal.SIGHUP,
}


def _stop_signal(name: str) -> int:
    sig = _SIGNALS.get(name)
    if sig is None:
        raise ProcessError(f"unknown signal {name!r}")
    return int(sig)


def _meta_path(root: Path, process_id: str) -> Path:
    return root / process_id / META_NAME


def _log_path(root: Path, process_id: str) -> Path:
    return root / process_id / LOG_NAME


def _load_meta(root: Path, process_id: str) -> dict | None:
    path = _meta_path(root, process_id)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except ValueError:
        return None


def _write_meta(root: Path, process_id: str, meta: dict) -> None:
    _meta_path(root, process_id).write_text(
        json.dumps(meta, ensure_ascii=False), encoding="utf-8"
    )


def _log_size(root: Path, process_id: str) -> int:
    try:
        return _log_path(root, process_id).stat().st_size
    except OSError:
        return 0


def start_process(
    root: Path,
    *,
    command: str,
    kind: str,
    cwd: str | None = None,
    ttl_seconds: int = 3600,
) -> dict:
    """Start a detached process and return its registry entry (meta)."""
    if kind not in VALID_KINDS:
        raise ProcessError(f"invalid kind {kind!r}")
    root.mkdir(parents=True, exist_ok=True)
    process_id = uuid4().hex
    proc_dir = root / process_id
    proc_dir.mkdir(parents=True)
    log_path = proc_dir / LOG_NAME

    log_handle = log_path.open("ab")
    # shell=True is the contract: the agent hands us a shell command line.
    # The process runs inside the pod's own sandbox as the same user.
    proc = subprocess.Popen(  # noqa: S602
        command,
        shell=True,
        cwd=cwd,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        stdin=subprocess.PIPE,
        start_new_session=True,  # setsid: outlives the daemon request
    )
    log_handle.close()
    _LIVE_POPEN[process_id] = proc
    now = time.time()
    meta = {
        "process_id": process_id,
        "pid": proc.pid,
        "command": command,
        "kind": kind,
        "started_at": now,
        "expires_at": now + ttl_seconds,
        "status": "running",
        "exit_code": None,
    }
    _write_meta(root, process_id, meta)
    return meta


def _refresh_status(root: Path, process_id: str, meta: dict) -> dict:
    """Derive liveness/expiry from the OS and persist the transition."""
    if meta.get("status") != "running":
        return meta
    pid = meta.get("pid")
    if not isinstance(pid, int) or not _pid_alive(pid):
        meta["status"] = "exited"
        _write_meta(root, process_id, meta)
        return meta
    if time.time() >= meta.get("expires_at", float("inf")):
        _stop_by_pid(pid=pid)
        meta["status"] = "reaped"
        meta["exit_code"] = 143
        _write_meta(root, process_id, meta)
    return meta


def read_output(
    root: Path, process_id: str, *, cursor: int = 0, max_bytes: int = 64 * 1024
) -> dict:
    """Incremental read from the output log: {chunk, new_cursor, status,
    exit_code}. The cursor is a byte offset; always advances to EOF."""
    meta = _load_meta(root, process_id)
    if meta is None:
        raise ProcessError(f"unknown process {process_id!r}")
    meta = _refresh_status(root, process_id, meta)
    log_path = _log_path(root, process_id)
    chunk = ""
    new_cursor = int(cursor)
    try:
        size = log_path.stat().st_size
    except OSError:
        size = 0
    if cursor < size:
        with log_path.open("rb") as f:
            f.seek(cursor)
            data = f.read(max_bytes)
        new_cursor = cursor + len(data)
        chunk = data.decode("utf-8", errors="replace")
    return {
        "chunk": chunk,
        "new_cursor": new_cursor,
        "size": size,
        "status": meta.get("status"),
        "exit_code": meta.get("exit_code"),
    }


def write_input(
    root: Path,  # noqa: ARG001 - API symmetry with the other entry points
    process_id: str,
    data: str,
) -> None:
    """Write to the process stdin. Only possible while this daemon holds the
    pipe — after a daemon restart the process is poll/stop-only."""
    proc = _LIVE_POPEN.get(process_id)
    if proc is None or proc.stdin is None:
        raise ProcessGoneError("process stdin is not connected (daemon restarted?)")
    try:
        proc.stdin.write(data.encode("utf-8"))
        proc.stdin.flush()
    except (BrokenPipeError, OSError) as e:
        raise ProcessGoneError("process stdin pipe is broken") from e


def stop_process(root: Path, process_id: str, *, signal_name: str = "TERM") -> dict:
    """Stop a running process: TERM (or the named signal), then KILL after
    the grace period. Returns the refreshed registry entry."""
    meta = _load_meta(root, process_id)
    if meta is None:
        raise ProcessError(f"unknown process {process_id!r}")
    meta = _refresh_status(root, process_id, meta)
    if meta.get("status") == "running":
        pid = meta.get("pid")
        if isinstance(pid, int):
            _stop_by_pid(pid=pid, signal_name=signal_name)
        meta["status"] = "reaped"
        meta["exit_code"] = 128 + _stop_signal(signal_name)
        _write_meta(root, process_id, meta)
    return meta


def _stop_by_pid(*, pid: int, signal_name: str = "TERM") -> None:
    if not isinstance(pid, int):
        return
    try:
        os.kill(pid, _stop_signal(signal_name))
    except ProcessLookupError:
        return
    if signal_name != "KILL":
        deadline = time.time() + _STOP_GRACE_SECONDS
        while time.time() < deadline and _pid_alive(pid):
            time.sleep(0.1)
        if _pid_alive(pid):
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


def list_processes(root: Path) -> list[dict]:
    """All registry entries, refreshed. Known-expired entries that were
    never reaped are marked (not deleted — the watch lane reports them)."""
    out: list[dict] = []
    if not root.exists():
        return out
    for proc_dir in sorted(root.iterdir()):
        if not proc_dir.is_dir():
            continue
        meta = _load_meta(root, proc_dir.name)
        if meta is None:
            continue
        out.append(_refresh_status(root, proc_dir.name, meta))
    return out


def count_running(root: Path) -> int:
    return sum(1 for m in list_processes(root) if m.get("status") == "running")
