# Sandbox daemon background-process data-plane client: thin signed HTTP
# wrappers over the daemon's /processes endpoints. Mirrors SidecarClient.

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any
from uuid import UUID

import httpx

from onyx.server.features.build.sandbox.image.sandbox_daemon.contract import (
    PROCESS_TTL_SECONDS,
    SIDECAR_PROCESS_INPUT_SUFFIX,
    SIDECAR_PROCESS_ITEM_PREFIX,
    SIDECAR_PROCESS_LIST_PATH,
    SIDECAR_PROCESS_POLL_SUFFIX,
    SIDECAR_PROCESS_START_PATH,
    SIDECAR_PROCESS_STOP_SUFFIX,
)


class ProcessClientError(RuntimeError):
    pass


class ProcessClient:
    """Signed HTTP client for the daemon's process endpoints. Per-backend
    managers supply ``host(sandbox_id) -> str`` (pod IP / container IP)."""

    def __init__(self, host: Callable[[UUID], str], signer) -> None:
        self._host = host
        self._sign = signer

    def _request(
        self,
        sandbox_id: UUID,
        method: str,
        endpoint_path: str,
        signing_path: str,
        body: dict[str, Any] | None = None,
        timeout: float = 30.0,
    ) -> Any:
        payload = json.dumps(body or {}).encode("utf-8")
        sha = __import__("hashlib").sha256(payload).hexdigest()
        sig, ts = self._sign(signing_path, sha)
        url = f"http://{self._host(sandbox_id)}:8731{endpoint_path}"
        with httpx.Client(timeout=timeout) as client:
            resp = client.request(
                method,
                url,
                content=payload if method in ("POST", "PUT") else None,
                headers={
                    "Content-Type": "application/json",
                    "X-Push-Signature": sig,
                    "X-Push-Timestamp": ts,
                },
            )
        if resp.status_code >= 400:
            raise ProcessClientError(
                f"process endpoint {endpoint_path} failed: {resp.status_code} "
                f"{resp.text[:200]}"
            )
        return resp.json() if method == "POST" else resp.json()

    def start(
        self, sandbox_id: UUID, *, command: str, kind: str = "background"
    ) -> dict[str, Any]:
        return self._request(
            sandbox_id,
            "POST",
            SIDECAR_PROCESS_START_PATH,
            SIDECAR_PROCESS_START_PATH,
            {"command": command, "kind": kind, "ttl_seconds": PROCESS_TTL_SECONDS},
        )

    def poll(
        self, sandbox_id: UUID, process_id: str, *, cursor: int, max_bytes: int
    ) -> dict[str, Any]:
        return self._request(
            sandbox_id,
            "POST",
            SIDECAR_PROCESS_ITEM_PREFIX.format(process_id=process_id)
            + SIDECAR_PROCESS_POLL_SUFFIX,
            SIDECAR_PROCESS_ITEM_PREFIX.format(process_id=process_id)
            + SIDECAR_PROCESS_POLL_SUFFIX,
            {"cursor": cursor, "max_bytes": max_bytes},
        )

    def write_input(self, sandbox_id: UUID, process_id: str, data: str) -> None:
        self._request(
            sandbox_id,
            "POST",
            SIDECAR_PROCESS_ITEM_PREFIX.format(process_id=process_id)
            + SIDECAR_PROCESS_INPUT_SUFFIX,
            SIDECAR_PROCESS_ITEM_PREFIX.format(process_id=process_id)
            + SIDECAR_PROCESS_INPUT_SUFFIX,
            {"data": data},
        )

    def stop(
        self, sandbox_id: UUID, process_id: str, *, signal_name: str = "TERM"
    ) -> dict[str, Any]:
        return self._request(
            sandbox_id,
            "POST",
            SIDECAR_PROCESS_ITEM_PREFIX.format(process_id=process_id)
            + SIDECAR_PROCESS_STOP_SUFFIX,
            SIDECAR_PROCESS_ITEM_PREFIX.format(process_id=process_id)
            + SIDECAR_PROCESS_STOP_SUFFIX,
            {"signal": signal_name},
        )

    def list_processes(self, sandbox_id: UUID) -> list[dict[str, Any]]:
        return self._request(
            sandbox_id, "GET", SIDECAR_PROCESS_LIST_PATH, SIDECAR_PROCESS_LIST_PATH
        )
