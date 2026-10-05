"""HTTP-level codex bridge e2e: real daemon server + fake codex binary.

The unit-tier contract tests drive ``CodexBridge`` in-process; this tier
runs the actual FastAPI daemon (Ed25519-signed routes, SSE streaming) and
drives it with the real host-side stack — ``CodexTransport`` +
``CodexServeClient`` + ``translate_codex_event`` — so every layer between
the executor and the child process is exercised except the real codex
binary itself.
"""

from __future__ import annotations

import base64
import importlib.util
import sys
import threading
import types
import uuid
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from tests.common.paths import find_ancestor_containing

_REPO_ROOT = find_ancestor_containing("backend/onyx")
_DAEMON_DIR = (
    _REPO_ROOT / "backend/onyx/server/features/build/sandbox/image/sandbox_daemon"
)

_FAKE_CODEX = r'''
import json
import sys

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
            "result": {"thread": {"id": "thr_e2e"}, "model": "gpt-e2e"},
        }) + "\n")
        sys.stdout.flush()
    elif method == "thread/inject_items":
        sys.stdout.write(json.dumps({"id": message["id"], "result": {"accepted": len(message.get("params", {}).get("items", []))}}) + "\n")
        sys.stdout.flush()
    elif method == "turn/start":
        sys.stdout.write(json.dumps({
            "id": message["id"], "result": {"turn": {"id": "t_e2e", "status": "running"}},
        }) + "\n")
        sys.stdout.write(json.dumps({
            "method": "item/agentMessage/delta",
            "params": {"threadId": "thr_e2e", "itemId": "m1", "delta": "你好，"},
        }) + "\n")
        sys.stdout.write(json.dumps({
            "method": "item/agentMessage/delta",
            "params": {"threadId": "thr_e2e", "itemId": "m1", "delta": "世界"},
        }) + "\n")
        sys.stdout.write(json.dumps({
            "method": "thread/tokenUsage/updated",
            "params": {"threadId": "thr_e2e", "tokenUsage": {
                "total": {"inputTokens": 120, "outputTokens": 8},
                "last": {"inputTokens": 120},
            }},
        }) + "\n")
        sys.stdout.write(json.dumps({
            "method": "turn/completed",
            "params": {"threadId": "thr_e2e", "turn": {"id": "t_e2e", "status": "completed"}},
        }) + "\n")
        sys.stdout.flush()
    elif method == "turn/interrupt":
        sys.stdout.write(json.dumps({"id": message["id"], "result": {}}) + "\n")
        sys.stdout.flush()
    else:
        sys.stdout.write(json.dumps({"id": message["id"], "result": {}}) + "\n")
        sys.stdout.flush()
'''


def _load_daemon_server() -> types.ModuleType:
    """Load sandbox_daemon.server like the sibling test file does."""
    if "sandbox_daemon.server" in sys.modules:
        return sys.modules["sandbox_daemon.server"]
    if "sandbox_daemon" not in sys.modules:
        sys.modules["sandbox_daemon"] = types.ModuleType("sandbox_daemon")
    for name in (
        "contract",
        "extract",
        "processes",
        "snapshot",
        "opencode_history",
        "filesystem",
        "manifest",
        "codex_bridge",
        "server",
    ):
        spec = importlib.util.spec_from_file_location(
            f"sandbox_daemon.{name}", str(_DAEMON_DIR / f"{name}.py")
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[f"sandbox_daemon.{name}"] = module
        spec.loader.exec_module(module)
    return sys.modules["sandbox_daemon.server"]


class _DaemonHandle:
    """Uvicorn server on an ephemeral port + Ed25519 signing pair."""

    def __init__(self, server_module, monkeypatch, tmp_path: Path) -> None:
        import uvicorn

        self.private_key = Ed25519PrivateKey.generate()
        public_b64 = base64.b64encode(
            self.private_key.public_key().public_bytes(
                Encoding.Raw, PublicFormat.Raw
            )
        ).decode()
        monkeypatch.setenv("ONYX_SANDBOX_PUSH_PUBLIC_KEY", public_b64)
        # The daemon caches the parsed key in a module global; reset it so
        # each test's fresh key pair takes effect.
        monkeypatch.setattr(server_module, "_public_key", None)

        fake_bin = tmp_path / "fake-codex"
        fake_bin.write_text("#!" + sys.executable + "\n" + _FAKE_CODEX)
        fake_bin.chmod(0o755)
        monkeypatch.setenv("CODEX_BIN", str(fake_bin))
        monkeypatch.setenv("CODEX_BRIDGE_CWD", str(tmp_path))
        monkeypatch.setenv("HOME", str(tmp_path))
        bridge_mod = sys.modules["sandbox_daemon.codex_bridge"]
        monkeypatch.setattr(bridge_mod, "CODEX_HOME", str(tmp_path / "codex-home"))
        monkeypatch.setattr(bridge_mod, "CODEX_ENV_FILE", str(tmp_path / "env"))
        monkeypatch.setattr(bridge_mod.CodexBridge, "_instance", None)
        monkeypatch.setattr(
            bridge_mod,
            "_PASSTHROUGH_ENV_KEYS",
            bridge_mod._PASSTHROUGH_ENV_KEYS,
        )

        config = uvicorn.Config(server_module.app, host="127.0.0.1", port=0, log_level="warning")
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._server.run, daemon=True)
        self._thread.start()
        for _ in range(100):
            if self._server.started:
                break
            import time

            time.sleep(0.05)
        assert self._server.started
        self.port = self._server.servers[0].sockets[0].getsockname()[1]

    def stop(self) -> None:
        self._server.should_exit = True
        self._thread.join(timeout=5)

    def signer(self):
        import hashlib
        import time as _time

        def sign(path: str, body_hash: str | None = None) -> tuple[str, str]:
            digest = body_hash or hashlib.sha256(b"").hexdigest()
            timestamp = str(int(_time.time()))
            message = f"{timestamp}|{path}|{digest}".encode()
            signature = base64.b64encode(self.private_key.sign(message)).decode()
            return signature, timestamp

        return sign


@pytest.fixture(autouse=True)
def _no_output_capture(request: pytest.FixtureRequest) -> None:
    """Run with real stdout/stderr fds.

    The daemon server, the SSE pump, and the fake codex child write from
    background contexts; pytest's fd-level capture deadlocks against
    them (passes under -s). Disabling fd capture keeps the e2e
    deterministic."""
    capfd = request.getfixturevalue("capfd")
    with capfd.disabled():
        yield


@pytest.fixture()
def daemon(monkeypatch, tmp_path):
    server_module = _load_daemon_server()
    from onyx.server.features.build.sandbox.codex.transport import CodexTransport

    handle = _DaemonHandle(server_module, monkeypatch, tmp_path)
    sandbox_id = uuid.uuid4()
    transport = CodexTransport(
        host=lambda _sid: "127.0.0.1",
        signer=handle.signer(),
        port=handle.port,
    )
    try:
        yield handle, transport, sandbox_id
    finally:
        handle.stop()


def test_codex_health_reflects_binary(daemon) -> None:
    _handle, transport, sandbox_id = daemon
    status = transport.health(sandbox_id)
    assert status["binary_available"] is True
    assert status["running"] is False  # health never spawns


def test_full_turn_over_http(daemon) -> None:
    """thread/start → inject → turn/start → streamed events → terminator,
    through signed HTTP + SSE, translated by the host stack."""
    from onyx.server.features.build.packets import ContextUsagePacket
    from onyx.server.features.build.sandbox.codex.serve_client import (
        CodexServeClient,
    )
    from onyx.server.features.build.sandbox.event_schema import (
        AgentMessageChunk,
        PromptResponse,
    )

    _handle, transport, sandbox_id = daemon
    client = CodexServeClient(transport, sandbox_id)
    thread_id = client.start_thread(
        cwd="/tmp",
        base_instructions="test instructions",
        model="gpt-e2e",
        inject_items=[
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "prior turn"}],
            }
        ],
    )
    assert thread_id == "thr_e2e"

    events = list(
        client.stream_turn(
            thread_id=thread_id,
            prompt="你好",
            timeout_s=20.0,
        )
    )
    chunks = [e for e in events if isinstance(e, AgentMessageChunk)]
    assert "".join(c.content.text for c in chunks) == "你好，世界"
    usage = [e for e in events if isinstance(e, ContextUsagePacket)]
    assert usage and usage[0].input_tokens == 120
    terminators = [e for e in events if isinstance(e, PromptResponse)]
    assert terminators and terminators[-1].stop_reason == "end_turn"


def test_rpc_error_surfaces_as_transport_error(daemon, monkeypatch, tmp_path) -> None:
    """A codex JSON-RPC error crosses the HTTP boundary intact."""
    _handle, transport, sandbox_id = daemon
    from onyx.server.features.build.sandbox.codex.transport import (
        CodexTransportError,
    )

    # Point the bridge at a fake that answers thread/start with an error.
    error_fake = tmp_path / "error-codex"
    error_fake.write_text(
        "#!" + sys.executable + "\n"
        "import json,sys\n"
        "for line in sys.stdin:\n"
        "    m=json.loads(line.strip() or '{}')\n"
        "    if 'id' in m:\n"
        "        sys.stdout.write(json.dumps({'id':m['id'],'error':{'code':400,'message':'model unavailable'}})+'\\n');sys.stdout.flush()\n"
    )
    error_fake.chmod(0o755)
    bridge_mod = sys.modules["sandbox_daemon.codex_bridge"]
    monkeypatch.setenv("CODEX_BIN", str(error_fake))
    monkeypatch.setattr(bridge_mod.CodexBridge, "_instance", None)
    with pytest.raises(CodexTransportError) as excinfo:
        transport.rpc(sandbox_id, "thread/start", {}, initialize=True, timeout_s=10)
    assert "model unavailable" in str(excinfo.value)
