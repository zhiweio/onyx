"""Signed HTTP transport to the sandbox daemon's codex bridge.

Mirrors ``ProcessClient``: per-backend managers already hold an Ed25519
signer and a host resolver for the daemon (port 8731); this module only
adds the two codex calls — one-shot RPC and the SSE notification stream.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from typing import Any
from uuid import UUID

import httpx

from onyx.server.features.build.sandbox.image.sandbox_daemon.contract import (
    SIDECAR_CODEX_EVENTS_PATH,
    SIDECAR_CODEX_HEALTH_PATH,
    SIDECAR_CODEX_RPC_PATH,
)

DAEMON_PORT = 8731


class CodexTransportError(RuntimeError):
    pass


class CodexTransport:
    """Per-manager transport; one instance serves every sandbox.

    ``client_factory`` overrides HTTP client construction (tests inject an
    ASGI-transported client to drive the daemon app in-process)."""

    def __init__(
        self,
        host: Callable[[UUID], str],
        signer,
        port: int = DAEMON_PORT,
        client_factory: "Callable[[], httpx.Client] | None" = None,
    ) -> None:
        self._host = host
        self._sign = signer
        self._port = port
        self._client_factory = client_factory

    def _client(self, timeout: float) -> httpx.Client:
        if self._client_factory is not None:
            return self._client_factory()
        return httpx.Client(timeout=timeout)

    def _url(self, sandbox_id: UUID, path: str) -> str:
        return f"http://{self._host(sandbox_id)}:{self._port}{path}"

    def _headers(self, path: str) -> dict[str, str]:
        # The daemon's process-auth verifies over the empty-body hash
        # regardless of payload (see server.py::_verify_process_auth).
        import hashlib

        body_hash = hashlib.sha256(b"").hexdigest()
        signature, timestamp = self._sign(path, body_hash)
        return {
            "X-Push-Signature": signature,
            "X-Push-Timestamp": timestamp,
        }

    def rpc(
        self,
        sandbox_id: UUID,
        method: str,
        params: dict[str, Any],
        *,
        initialize: bool = False,
        timeout_s: float = 60.0,
    ) -> Any:
        url = self._url(sandbox_id, SIDECAR_CODEX_RPC_PATH)
        body = {
            "method": method,
            "params": params,
            "initialize": initialize,
            "timeout_ms": int(timeout_s * 1000),
        }
        try:
            with self._client(timeout_s + 10.0) as client:
                resp = client.post(
                    url,
                    content=json.dumps(body).encode("utf-8"),
                    headers={
                        "Content-Type": "application/json",
                        **self._headers(SIDECAR_CODEX_RPC_PATH),
                    },
                )
        except httpx.HTTPError as exc:
            raise CodexTransportError(f"codex rpc transport failed: {exc}") from exc
        if resp.status_code == 501:
            raise CodexTransportError(
                "codex runtime unavailable in this sandbox (image built without "
                "ENABLE_CODEX)"
            )
        if resp.status_code >= 400:
            raise CodexTransportError(
                f"codex rpc failed: {resp.status_code} {resp.text[:200]}"
            )
        payload = resp.json()
        if not payload.get("ok"):
            raise CodexTransportError(str(payload.get("error") or "unknown error"))
        return payload.get("result")

    def health(self, sandbox_id: UUID) -> dict[str, Any]:
        """Bridge status: binary presence + running process (never spawns)."""
        url = self._url(sandbox_id, SIDECAR_CODEX_HEALTH_PATH)
        try:
            with self._client(10.0) as client:
                resp = client.get(
                    url, headers=self._headers(SIDECAR_CODEX_HEALTH_PATH)
                )
        except httpx.HTTPError as exc:
            raise CodexTransportError(f"codex health failed: {exc}") from exc
        if resp.status_code >= 400:
            raise CodexTransportError(f"codex health failed: {resp.status_code}")
        return resp.json()

    def events(self, sandbox_id: UUID) -> Iterator[dict[str, Any]]:
        """Bridge notification stream, subscribed EAGERLY.

        The server broadcasts to current subscribers only, so the
        subscription must be live before the caller starts a turn. This
        method is NOT a generator: it starts the SSE pump thread now,
        waits (≤10s) for the server to register the subscription, and
        returns a lazy drain generator. Closing that generator stops the
        pump. (A generator function would defer all of this to the first
        next() — after the turn already started.)"""
        import threading
        from queue import SimpleQueue

        url = self._url(sandbox_id, SIDECAR_CODEX_EVENTS_PATH)
        queue_out: SimpleQueue = SimpleQueue()
        connected = threading.Event()
        failed: list[str] = []
        end = object()
        stop = threading.Event()

        def _pump() -> None:
            try:
                with self._client(None) as client:
                    with client.stream(
                        "GET", url, headers=self._headers(SIDECAR_CODEX_EVENTS_PATH)
                    ) as resp:
                        if resp.status_code >= 400:
                            failed.append(f"codex events failed: {resp.status_code}")
                            return
                        connected.set()
                        for line in resp.iter_lines():
                            if stop.is_set():
                                return
                            if not line.startswith("data: "):
                                continue  # keepalives (": keepalive") and blanks
                            try:
                                message = json.loads(line[len("data: ") :])
                            except ValueError:
                                continue
                            if isinstance(message, dict):
                                queue_out.put(message)
            except Exception as exc:  # pump dies with the connection
                if not connected.is_set():
                    failed.append(f"codex events connect failed: {exc}")
            finally:
                queue_out.put(end)

        thread = threading.Thread(target=_pump, daemon=True, name="codex-sse-pump")
        thread.start()
        if not connected.wait(timeout=10.0):
            stop.set()
            raise CodexTransportError("codex events subscription never connected")
        if failed:
            stop.set()
            raise CodexTransportError(failed[0])

        def _drain() -> Iterator[dict[str, Any]]:
            try:
                while True:
                    item = queue_out.get()
                    if item is end:
                        return
                    yield item
            finally:
                stop.set()

        return _drain()
