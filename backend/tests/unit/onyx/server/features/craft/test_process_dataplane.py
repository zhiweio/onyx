"""Sandbox daemon process data plane: lifecycle, cursor reads, stop, routes.

Behavior tests over the daemon's /processes endpoints and the underlying
processes module, reusing the dynamic loader (the daemon is a top-level
package inside the pod image).
"""

from __future__ import annotations

import sys
import time

import pytest
from fastapi.testclient import TestClient

from tests.unit.onyx.server.features.craft.sandbox.sandbox_daemon.test_sandbox_daemon import (
    _load_sandbox_daemon_modules,
)

# Load the daemon package dynamically BEFORE importing its submodules: the
# container layout (sandbox_daemon on the pod path) isn't on the host path.
_load_sandbox_daemon_modules()
processes = sys.modules["sandbox_daemon.processes"]
daemon_server = sys.modules["sandbox_daemon.server"]


@pytest.fixture
def proc_root(tmp_path):
    return tmp_path / "processes"


@pytest.fixture
def client(monkeypatch, proc_root):
    monkeypatch.setattr(daemon_server, "PROCESS_ROOT", proc_root)
    monkeypatch.setattr(daemon_server, "_process_token", lambda: "test-token")
    from sandbox_daemon.contract import (  # ty: ignore[unresolved-import]
        SIDECAR_PROCESS_ITEM_PREFIX,
        SIDECAR_PROCESS_LIST_PATH,
        SIDECAR_PROCESS_POLL_SUFFIX,
        SIDECAR_PROCESS_START_PATH,
        SIDECAR_PROCESS_STOP_SUFFIX,
    )

    class _Routes:
        start = SIDECAR_PROCESS_START_PATH
        poll = SIDECAR_PROCESS_ITEM_PREFIX + SIDECAR_PROCESS_POLL_SUFFIX
        stop = SIDECAR_PROCESS_ITEM_PREFIX + SIDECAR_PROCESS_STOP_SUFFIX
        list_ = SIDECAR_PROCESS_LIST_PATH

    return TestClient(daemon_server.app), _Routes()


def _auth(_client):
    return {"Authorization": "Bearer test-token"}


def _wait_output_size(proc_root, process_id, min_size: int, timeout: float = 5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if processes._log_size(proc_root, process_id) >= min_size:
            return
        time.sleep(0.05)
    raise AssertionError(f"output of {process_id} never reached {min_size} bytes")


def _wait_status(proc_root, process_id, status, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        meta = processes._load_meta(proc_root, process_id) or {}
        if meta.get("status") == status:
            return meta
        time.sleep(0.05)
    raise AssertionError(f"process {process_id} never reached {status!r}")


def test_start_process_registers_and_runs(proc_root) -> None:
    meta = processes.start_process(
        proc_root, command="sleep 30", kind="background", ttl_seconds=300
    )
    assert meta["status"] == "running"
    assert (proc_root / meta["process_id"] / "output.log").exists()
    entries = processes.list_processes(proc_root)
    assert [m["process_id"] for m in entries] == [meta["process_id"]]


def test_start_process_rejects_unknown_kind(proc_root) -> None:
    with pytest.raises(processes.ProcessError):
        processes.start_process(proc_root, command="x", kind="hax")


def test_read_output_paginates_by_cursor(proc_root) -> None:
    meta = processes.start_process(
        proc_root, command="printf 'abcdefghij'", kind="background"
    )
    process_id = meta["process_id"]
    _wait_output_size(proc_root, process_id, 10)
    first = processes.read_output(proc_root, process_id, cursor=0, max_bytes=4)
    assert first["chunk"] == "abcd"
    assert first["new_cursor"] == 4
    second = processes.read_output(proc_root, process_id, cursor=4, max_bytes=64)
    assert second["chunk"] == "efghij"
    assert second["new_cursor"] == 10


def test_read_output_unknown_process_raises(proc_root) -> None:
    with pytest.raises(processes.ProcessError):
        processes.read_output(proc_root, "nope", cursor=0)


def test_stop_process_reaps(proc_root) -> None:
    meta = processes.start_process(proc_root, command="sleep 30", kind="background")
    result = processes.stop_process(proc_root, meta["process_id"])
    assert result["status"] == "reaped"
    assert result["exit_code"] == 128 + 15  # SIGTERM


def test_expired_process_is_reaped_by_refresh(proc_root) -> None:
    meta = processes.start_process(
        proc_root, command="sleep 30", kind="background", ttl_seconds=0
    )
    result = processes.read_output(proc_root, meta["process_id"], cursor=0)
    assert result["status"] == "reaped"
    assert result["exit_code"] == 143


def test_write_input_requires_live_daemon_pipe(proc_root) -> None:
    meta = processes.start_process(
        proc_root, command="cat > out.txt", kind="background"
    )
    processes._LIVE_POPEN.clear()
    with pytest.raises(processes.ProcessGoneError):
        processes.write_input(proc_root, meta["process_id"], "hi\n")


def test_routes_require_auth(client) -> None:
    tc, routes = client
    assert tc.post(routes.start, json={"command": "x"}).status_code == 401
    assert (
        tc.post(routes.poll.format(process_id="x"), json={"cursor": 0}).status_code
        == 401
    )


def test_routes_start_poll_stop_roundtrip(client, proc_root) -> None:
    tc, routes = client
    headers = {"Authorization": "Bearer test-token"}

    started = tc.post(
        routes.start,
        json={"command": "printf 'hi from proc'", "kind": "background"},
        headers=headers,
    )
    assert started.status_code == 200
    process_id = started.json()["process_id"]
    _wait_output_size(proc_root, process_id, len("hi from proc"))

    polled = tc.post(
        routes.poll.format(process_id=process_id),
        json={"cursor": 0},
        headers=headers,
    )
    assert polled.status_code == 200
    body = polled.json()
    assert "hi from proc" in body["chunk"]
    assert body["status"] == "running"

    stopped = tc.post(
        routes.stop.format(process_id=process_id), json={}, headers=headers
    )
    assert stopped.status_code == 200
    assert stopped.json()["status"] == "reaped"


def test_routes_list_and_unknown_process(client) -> None:
    tc, routes = client
    headers = {"Authorization": "Bearer test-token"}
    assert tc.get(routes.list_, headers=headers).status_code == 200

    missing = tc.post(
        routes.poll.format(process_id="missing"),
        json={"cursor": 0},
        headers=headers,
    )
    assert missing.status_code == 404
