"""codex app-server bridge: child process + JSONL RPC + event broadcast.

The codex CLI speaks a newline-delimited JSON-RPC on stdio
(``codex app-server``). This module owns that child process for the
sandbox lifetime and exposes it to the host as plain HTTP: one-shot RPC
requests and an SSE stream of every notification. The bridge itself is
stateless protocol plumbing — sessions, history, and auth live with the
platform (the tape) and the config files the host writes.

Process discipline: lazy start on first use, respawn on next use after a
crash (short backoff), one writer lock for stdin, and a bounded stderr
tail for diagnostics. ``CODEX_ENV_FILE`` (KEY=VALUE lines, written by the
host next to config.toml) carries gateway credentials into the child
environment.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
from collections import deque
from queue import SimpleQueue
from typing import Any

CODEX_BIN_ENV = "CODEX_BIN"
CODEX_HOME = "/workspace/codex-home"
CODEX_ENV_FILE = "/workspace/managed/codex-env"
# cwd for the child (the sandbox workspace root); overridable for tests.
CODEX_BRIDGE_CWD_ENV = "CODEX_BRIDGE_CWD"
CODEX_BRIDGE_CWD_DEFAULT = "/workspace"

# Environment keys the child inherits from the daemon. Mirrors qm's
# passthrough list: locale, TLS roots, and the egress proxy set (the
# platform's network policy applies to codex exactly as to opencode).
_PASSTHROUGH_ENV_KEYS = (
    "PATH",
    "TMPDIR",
    "LANG",
    "LC_ALL",
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
    "NODE_EXTRA_CA_CERTS",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "NO_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "no_proxy",
    "all_proxy",
)

_STDERR_TAIL_LINES = 200
_RESTART_BACKOFF_SECONDS = 1.0
_EXIT_NOTIFICATION = {"method": "codex/exit"}


class CodexBridgeError(RuntimeError):
    pass


class _Pending:
    """One in-flight request: the reader sets the response and wakes us."""

    __slots__ = ("event", "message")

    def __init__(self) -> None:
        self.event = threading.Event()
        self.message: dict[str, Any] | None = None


class CodexBridge:
    """Singleton per daemon process."""

    _instance: "CodexBridge | None" = None
    _instance_lock = threading.Lock()

    def __init__(self) -> None:
        self._lock = threading.Lock()  # serializes spawn + stdin writes
        self._process: subprocess.Popen[bytes] | None = None
        self._next_id = 0
        self._pending: dict[int, _Pending] = {}
        self._subscribers: list[SimpleQueue] = []
        self._subscribers_lock = threading.Lock()
        self._stderr_tail: deque[str] = deque(maxlen=_STDERR_TAIL_LINES)
        self._last_death_at: float | None = None
        self._initialized = False

    @classmethod
    def instance(cls) -> "CodexBridge":
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = CodexBridge()
            return cls._instance

    # ── lifecycle ─────────────────────────────────────────────────────

    def _binary_or_none(self) -> str | None:
        candidate = os.environ.get(CODEX_BIN_ENV, "").strip() or shutil.which("codex")
        if candidate and os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
        return None

    def _binary(self) -> str:
        binary = self._binary_or_none()
        if not binary:
            raise CodexBridgeError(
                "codex binary not found; build the sandbox image with ENABLE_CODEX"
            )
        return binary

    def _child_env(self) -> dict[str, str]:
        env = {
            key: os.environ[key] for key in _PASSTHROUGH_ENV_KEYS if key in os.environ
        }
        env["HOME"] = "/home/sandbox"
        env["CODEX_HOME"] = CODEX_HOME
        try:
            os.makedirs(CODEX_HOME, exist_ok=True)
            with open(CODEX_ENV_FILE, encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, _, value = line.partition("=")
                    env[key.strip()] = value.strip()
        except OSError:
            pass
        return env

    def _alive(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def _ensure_started(self) -> None:
        if self._alive():
            return
        with self._lock:
            if self._alive():
                return
            if (
                self._last_death_at is not None
                and time.monotonic() - self._last_death_at < _RESTART_BACKOFF_SECONDS
            ):
                raise CodexBridgeError("codex app-server restarting; retry shortly")
            binary = self._binary()
            try:
                self._process = subprocess.Popen(
                    [binary, "app-server"],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=self._child_env(),
                    cwd=os.environ.get(CODEX_BRIDGE_CWD_ENV, CODEX_BRIDGE_CWD_DEFAULT),
                    start_new_session=True,
                )
            except OSError as exc:
                raise CodexBridgeError(f"failed to spawn codex: {exc}") from exc
            self._initialized = False
            threading.Thread(
                target=self._read_loop, name="codex-bridge-reader", daemon=True
            ).start()
            threading.Thread(
                target=self._drain_stderr, name="codex-bridge-stderr", daemon=True
            ).start()

    def _read_loop(self) -> None:
        process = self._process
        if process is None or process.stdout is None:
            return
        try:
            for line in iter(process.stdout.readline, b""):
                text = line.decode("utf-8", errors="replace").strip()
                if not text:
                    continue
                try:
                    message = json.loads(text)
                except ValueError:
                    self._stderr_tail.append(f"stdout-unparsable: {text[:200]}")
                    continue
                if not isinstance(message, dict):
                    continue
                # Response to one of our requests: hand it to the waiter.
                if (
                    "id" in message
                    and "method" not in message
                    and ("result" in message or "error" in message)
                ):
                    self._resolve_responses(message)
                    continue
                # Server→client request: acknowledge so codex proceeds.
                if "id" in message and "method" in message:
                    self._send_raw(
                        {"id": message["id"], "result": {}}, acquire_lock=False
                    )
                # Notification: broadcast to every SSE subscriber.
                self._broadcast(message)
        finally:
            self._mark_dead()

    def _resolve_responses(self, message: dict[str, Any]) -> bool:
        """Route a response frame to its waiter. True when consumed."""
        request_id = message.get("id")
        if not isinstance(request_id, int):
            return False
        if "result" not in message and "error" not in message:
            return False
        pending = self._pending.get(request_id)
        if pending is None:
            return False
        pending.message = message
        pending.event.set()
        return True

    def _mark_dead(self) -> None:
        self._last_death_at = time.monotonic()
        # The respawned process needs a fresh handshake.
        self._initialized = False
        for pending in list(self._pending.values()):
            pending.event.set()  # message stays None → "process exited"
        self._broadcast(_EXIT_NOTIFICATION)

    def _drain_stderr(self) -> None:
        process = self._process
        if process is None or process.stderr is None:
            return
        try:
            for raw in iter(process.stderr.readline, b""):
                self._stderr_tail.append(
                    raw.decode("utf-8", errors="replace").rstrip()[:400]
                )
        except OSError:
            pass

    # ── rpc ───────────────────────────────────────────────────────────

    def _send_raw(self, frame: dict[str, Any], *, acquire_lock: bool = True) -> None:
        process = self._process
        if process is None or process.stdin is None:
            raise CodexBridgeError("codex process not running")
        payload = json.dumps(frame).encode("utf-8") + b"\n"

        def _write() -> None:
            try:
                process.stdin.write(payload)  # type: ignore[union-attr]
                process.stdin.flush()  # type: ignore[union-attr]
            except (BrokenPipeError, OSError) as exc:
                raise CodexBridgeError(f"codex stdin write failed: {exc}") from exc

        if acquire_lock:
            with self._lock:
                _write()
        else:
            _write()

    def rpc(self, method: str, params: dict[str, Any], *, timeout: float = 30.0) -> Any:
        self._ensure_started()
        with self._lock:
            self._next_id += 1
            request_id = self._next_id
        pending = _Pending()
        self._pending[request_id] = pending
        try:
            self._send_raw({"id": request_id, "method": method, "params": params})
        except CodexBridgeError:
            self._pending.pop(request_id, None)
            raise
        try:
            if not pending.event.wait(timeout):
                raise CodexBridgeError(f"codex rpc timeout: {method}")
        finally:
            self._pending.pop(request_id, None)
        message = pending.message
        if message is None:
            raise CodexBridgeError("codex process exited during rpc")
        if "error" in message:
            error = message["error"]
            if isinstance(error, dict):
                raise CodexBridgeError(
                    f"codex error {error.get('code')}: {error.get('message')}"
                )
            raise CodexBridgeError(f"codex error: {error}")
        return message.get("result")

    def initialize(self) -> None:
        """Handshake once per process lifetime (idempotent)."""
        if self._initialized:
            return
        self.rpc(
            "initialize",
            {
                "clientInfo": {
                    "name": "onyx-craft",
                    "title": "Onyx Craft",
                    "version": "1",
                },
                "capabilities": {"experimentalApi": True},
            },
        )
        self.notify("initialized")
        self._initialized = True

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        self._ensure_started()
        self._send_raw({"method": method, "params": params or {}})

    # ── events ────────────────────────────────────────────────────────

    def _broadcast(self, message: dict[str, Any]) -> None:
        with self._subscribers_lock:
            subscribers = list(self._subscribers)
        for sub in subscribers:
            sub.put(message)

    def subscribe(self) -> SimpleQueue:
        sub: SimpleQueue = SimpleQueue()
        with self._subscribers_lock:
            self._subscribers.append(sub)
        return sub

    def unsubscribe(self, sub: SimpleQueue) -> None:
        with self._subscribers_lock:
            try:
                self._subscribers.remove(sub)
            except ValueError:
                pass

    # ── status ────────────────────────────────────────────────────────

    def status(self) -> dict[str, Any]:
        return {
            "binary_available": self._binary_or_none() is not None,
            "running": self._alive(),
            "stderr_tail": list(self._stderr_tail)[-20:],
        }
