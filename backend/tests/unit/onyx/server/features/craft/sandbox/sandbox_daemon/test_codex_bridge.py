"""codex bridge contract tests against a scripted fake app-server.

The fake binary speaks the same JSONL protocol the real codex CLI does,
so these tests pin the bridge's process discipline and framing without
the real binary.
"""

from __future__ import annotations

import importlib.util
import sys
import time
import types
from pathlib import Path

from tests.common.paths import find_ancestor_containing

_REPO_ROOT = find_ancestor_containing("backend/onyx")
_DAEMON_DIR = (
    _REPO_ROOT / "backend/onyx/server/features/build/sandbox/image/sandbox_daemon"
)

_FAKE_CODEX = r"""
import json
import os
import sys

counter_file = os.environ["FAKE_CODEX_COUNTER"]
with open(counter_file, "a", encoding="utf-8") as fh:
    fh.write("spawn\n")

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    message = json.loads(line)
    if "id" not in message:
        continue
    method = message.get("method", "")
    if method == "initialize":
        sys.stdout.write(json.dumps({"id": message["id"], "result": {"ok": True}}) + "\n")
        sys.stdout.flush()
    elif method == "thread/start":
        sys.stdout.write(json.dumps({
            "id": message["id"],
            "result": {"thread": {"id": "thr_1"}, "model": "gpt-test"},
        }) + "\n")
        sys.stdout.flush()
        sys.stdout.write(json.dumps({
            "method": "item/started",
            "params": {"threadId": "thr_1", "item": {"id": "it_1", "type": "agentMessage"}},
        }) + "\n")
        sys.stdout.write(json.dumps({
            "method": "turn/completed",
            "params": {"threadId": "thr_1", "turn": {"id": "t_1", "status": "completed"}},
        }) + "\n")
        sys.stdout.flush()
    elif method == "turn/start":
        sys.stdout.write(json.dumps({"id": message["id"], "result": {"turn": {"id": "t_1", "status": "running"}}}) + "\n")
        sys.stdout.flush()
    elif method == "die":
        sys.stdout.write(json.dumps({"id": message["id"], "result": {}}) + "\n")
        sys.stdout.flush()
        sys.exit(0)
    else:
        sys.stdout.write(json.dumps({"id": message["id"], "result": {}}) + "\n")
        sys.stdout.flush()
"""


def _load_bridge():
    if "sandbox_daemon.codex_bridge" in sys.modules:
        return sys.modules["sandbox_daemon.codex_bridge"]
    if "sandbox_daemon" not in sys.modules:
        sys.modules["sandbox_daemon"] = types.ModuleType("sandbox_daemon")
    spec = importlib.util.spec_from_file_location(
        "sandbox_daemon.codex_bridge", str(_DAEMON_DIR / "codex_bridge.py")
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["sandbox_daemon.codex_bridge"] = module
    spec.loader.exec_module(module)
    return module


def _fresh_bridge(monkeypatch, tmp_path: Path):
    bridge_mod = _load_bridge()
    fake_bin = tmp_path / "fake-codex"
    fake_bin.write_text(f"#!{sys.executable}\n" + _FAKE_CODEX)
    fake_bin.chmod(0o755)
    counter = tmp_path / "spawns.txt"
    monkeypatch.setenv("CODEX_BIN", str(fake_bin))
    monkeypatch.setenv("FAKE_CODEX_COUNTER", str(counter))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(bridge_mod.CodexBridge, "_instance", None)
    monkeypatch.setattr(bridge_mod, "CODEX_HOME", str(tmp_path / "codex-home"))
    monkeypatch.setattr(bridge_mod, "CODEX_ENV_FILE", str(tmp_path / "no-env-file"))
    monkeypatch.setenv("CODEX_BRIDGE_CWD", str(tmp_path))
    # The fake binary needs its counter-file env var to survive the
    # bridge's passthrough whitelist.
    monkeypatch.setattr(
        bridge_mod,
        "_PASSTHROUGH_ENV_KEYS",
        bridge_mod._PASSTHROUGH_ENV_KEYS + ("FAKE_CODEX_COUNTER",),
    )
    bridge = bridge_mod.CodexBridge.instance()
    return bridge_mod, bridge, counter


def test_rpc_roundtrip_and_notifications(monkeypatch, tmp_path) -> None:
    _, bridge, _counter = _fresh_bridge(monkeypatch, tmp_path)
    sub = bridge.subscribe()
    bridge.initialize()
    result = bridge.rpc("thread/start", {"cwd": "/workspace"})
    assert result == {"thread": {"id": "thr_1"}, "model": "gpt-test"}
    first = sub.get(timeout=5.0)
    assert first["method"] == "item/started"
    second = sub.get(timeout=5.0)
    assert second["method"] == "turn/completed"
    bridge.unsubscribe(sub)


def test_initialize_is_idempotent_per_process(monkeypatch, tmp_path) -> None:
    _, bridge, counter = _fresh_bridge(monkeypatch, tmp_path)
    bridge.initialize()
    bridge.initialize()
    # One spawn serves both initialize calls.
    time.sleep(0.3)
    assert counter.read_text().count("spawn") == 1


def test_exit_broadcast_and_respawn(monkeypatch, tmp_path) -> None:
    _, bridge, counter = _fresh_bridge(monkeypatch, tmp_path)
    sub = bridge.subscribe()
    bridge.initialize()
    # "die" makes the fake exit right after answering.
    bridge.rpc("die", {})
    message = sub.get(timeout=5.0)
    assert message == {"method": "codex/exit"}

    # Next use respawns (after the backoff window).
    time.sleep(1.2)
    bridge.initialize()
    assert counter.read_text().count("spawn") >= 2
    bridge.unsubscribe(sub)


def test_env_file_keys_reach_child(monkeypatch, tmp_path) -> None:
    bridge_mod, bridge, _counter = _fresh_bridge(monkeypatch, tmp_path)
    env_file = tmp_path / "codex-env"
    env_file.write_text("# comment\nONYX_CODEX_API_KEY=sk-test-123\nBADLINE\n")
    monkeypatch.setattr(bridge_mod, "CODEX_ENV_FILE", str(env_file))
    env = bridge._child_env()
    assert env["ONYX_CODEX_API_KEY"] == "sk-test-123"
    assert "BADLINE" not in env


def test_status_reports_missing_binary(monkeypatch, tmp_path) -> None:
    bridge_mod, bridge, _counter = _fresh_bridge(monkeypatch, tmp_path)
    monkeypatch.setenv("CODEX_BIN", str(tmp_path / "missing"))
    status = bridge.status()
    assert status["running"] is False
    assert status["binary_available"] is False
    try:
        bridge.rpc("initialize", {})
    except bridge_mod.CodexBridgeError as exc:
        assert "codex binary not found" in str(exc)
    else:
        raise AssertionError("expected CodexBridgeError")
