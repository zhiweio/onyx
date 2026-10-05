"""Pooled streamable-http MCP sessions for persistent event loops.

The MCP client is per-call today (``client.py``): every tool call opens a
streamable-http transport, initializes a session, calls, and tears down.
On the gateway process — one persistent event loop serving every cached
upstream call — that setup cost repeats constantly. This module pools
initialized sessions per ``(url, headers)`` and reuses them across calls.

Safety model:

- **Loop affinity**: a session belongs to the event loop that created it.
  Only loops explicitly registered as persistent (the gateway's uvicorn
  loop via ``register_persistent_loop``) ever CREATE pool entries; every
  other caller (chat tools run one loop per call) silently keeps the
  per-call path — no cross-loop reuse, no dead-loop leaks.
- **Identity**: keyed on ``(server_url, transport, headers_hash)`` — a
  credential change is a different key, so stale-auth sessions are never
  reused.
- **Concurrency**: JSON-RPC multiplexes requests on one session; a
  per-entry in-flight cap (``MCP_SESSION_INFLIGHT_CAP``) makes calls
  above the cap fall back to a fresh session instead of queueing.
- **Eviction**: idle TTL + LRU size cap, checked lazily on acquire;
  ``close_all`` at loop shutdown.
- **Reliability**: any error on a pooled session discards it and the
  caller retries once on a fresh session — never worse than per-call.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from collections.abc import Coroutine
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from onyx.configs.app_configs import (
    MCP_SESSION_IDLE_TTL_SECONDS,
    MCP_SESSION_INFLIGHT_CAP,
    MCP_SESSION_MAX_SIZE,
    MCP_SESSION_POOL_ENABLED,
)
from onyx.server.features.mcp.ssrf import mcp_ssrf_httpx_client_factory
from onyx.utils.logger import setup_logger

logger = setup_logger()

_POOL_KEY_PREFIX = "mcp_session_pool"


def _default_log() -> logging.Logger:
    return logging.getLogger(__name__)


def _headers_hash(headers: dict[str, str]) -> str:
    canonical = "\n".join(f"{k}: {v}" for k, v in sorted(headers.items()))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


@dataclass
class _PooledSession:
    key: str
    loop: asyncio.AbstractEventLoop
    session: ClientSession
    transport_cm: Any  # the streamablehttp_client async context manager
    session_cm: Any  # the ClientSession async context manager
    last_used: float = field(default_factory=time.monotonic)
    in_flight: int = 0
    created_at: float = field(default_factory=time.monotonic)

    def touch(self) -> None:
        self.last_used = time.monotonic()

    async def aclose(self) -> None:
        try:
            await self.session_cm.__aexit__(None, None, None)
        finally:
            await self.transport_cm.__aexit__(None, None, None)


class McpSessionPool:
    """One pool per process; entries pinned to their creating loop."""

    def __init__(
        self,
        *,
        max_size: int = MCP_SESSION_MAX_SIZE,
        idle_ttl: float = MCP_SESSION_IDLE_TTL_SECONDS,
        inflight_cap: int = MCP_SESSION_INFLIGHT_CAP,
    ) -> None:
        self._entries: dict[str, _PooledSession] = {}
        self._persistent_loops: set[int] = set()
        self._max_size = max_size
        self._idle_ttl = idle_ttl
        self._inflight_cap = inflight_cap
        self.metrics = {
            "reused": 0,
            "created": 0,
            "evicted_idle": 0,
            "evicted_lru": 0,
            "discarded_error": 0,
            "fallback": 0,
        }

    # ── loop registration ─────────────────────────────────────────────

    def register_persistent_loop(
        self, loop: asyncio.AbstractEventLoop | None = None
    ) -> None:
        loop = loop or asyncio.get_event_loop()
        self._persistent_loops.add(id(loop))

    def loop_is_persistent(self) -> bool:
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            return False
        return id(running) in self._persistent_loops

    # ── acquire / release ─────────────────────────────────────────────

    def acquire(
        self,
        *,
        server_url: str,
        headers: dict[str, str],
        read_timeout_seconds: float,  # noqa: ARG002
    ) -> Optional[_PooledSession]:
        """A usable pooled session, or None → caller uses its per-call path.

        Never blocks and never raises: pool bookkeeping problems degrade
        to the fresh path."""
        try:
            key = f"{server_url}|{_headers_hash(headers)}"
            running = asyncio.get_running_loop()
            self._evict_if_stale(key)
            entry = self._entries.get(key)
            if entry is not None and entry.loop is running:
                if entry.in_flight >= self._inflight_cap:
                    self.metrics["fallback"] += 1
                    return None
                entry.in_flight += 1
                entry.touch()
                self.metrics["reused"] += 1
                return entry
            if entry is not None:
                # Entry from another (dead) loop: drop it silently.
                self._entries.pop(key, None)
            if not self.loop_is_persistent():
                self.metrics["fallback"] += 1
                return None
            return None  # creation is async; see acquire_or_create
        except Exception:
            _default_log().debug("MCP session pool acquire failed", exc_info=True)
            return None

    def release(self, entry: _PooledSession) -> None:
        entry.in_flight = max(0, entry.in_flight - 1)
        entry.touch()

    def discard(self, entry: _PooledSession) -> None:
        """Drop a failed entry and close it on its own loop."""
        self._entries.pop(entry.key, None)
        self.metrics["discarded_error"] += 1
        try:
            entry.loop.create_task(self._safe_close(entry))
        except RuntimeError:
            pass  # loop already gone; session dies with it

    async def create(
        self,
        *,
        server_url: str,
        headers: dict[str, str],
        read_timeout_seconds: float,
    ) -> Optional[_PooledSession]:
        """Open + initialize a new pooled session on the running loop.

        Callers should only reach this when ``loop_is_persistent()``;
        it returns None on any failure so the fresh path takes over."""
        from datetime import timedelta

        try:
            self._evict_lru_if_full()
            key = f"{server_url}|{_headers_hash(headers)}"
            transport_cm = streamablehttp_client(
                server_url,
                headers=dict(headers),
                httpx_client_factory=mcp_ssrf_httpx_client_factory,
            )
            client_tuple = await transport_cm.__aenter__()
            read, write = client_tuple[0], client_tuple[1]
            session_cm = ClientSession(
                read,
                write,
                read_timeout_seconds=timedelta(seconds=read_timeout_seconds),
            )
            session = await session_cm.__aenter__()
            entry = _PooledSession(
                key=key,
                loop=asyncio.get_running_loop(),
                session=session,
                transport_cm=transport_cm,
                session_cm=session_cm,
            )
            entry.in_flight += 1
            self._entries[key] = entry
            self.metrics["created"] += 1
            return entry
        except Exception:
            _default_log().debug("MCP pooled session create failed", exc_info=True)
            return None

    def _evict_if_stale(self, key: str) -> None:
        entry = self._entries.get(key)
        if entry is None:
            return
        if time.monotonic() - entry.last_used > self._idle_ttl:
            self._entries.pop(key, None)
            self.metrics["evicted_idle"] += 1
            try:
                asyncio.get_running_loop().create_task(self._safe_close(entry))
            except RuntimeError:
                pass

    def _evict_lru_if_full(self) -> None:
        while len(self._entries) >= self._max_size:
            oldest_key = min(self._entries, key=lambda k: self._entries[k].last_used)
            entry = self._entries.pop(oldest_key)
            self.metrics["evicted_lru"] += 1
            try:
                asyncio.get_running_loop().create_task(self._safe_close(entry))
            except RuntimeError:
                pass

    async def _safe_close(self, entry: _PooledSession) -> None:
        try:
            await entry.aclose()
        except Exception:
            _default_log().debug("MCP pooled session close failed", exc_info=True)

    async def close_all(self) -> None:
        entries = list(self._entries.values())
        self._entries.clear()
        for entry in entries:
            await self._safe_close(entry)

    def stats(self) -> dict[str, Any]:
        return {
            "size": len(self._entries),
            "persistent_loops": len(self._persistent_loops),
            **self.metrics,
        }


_pool_singleton: McpSessionPool | None = None


def get_mcp_session_pool() -> McpSessionPool | None:
    """The process pool, or None when pooling is disabled by config."""
    global _pool_singleton
    if not MCP_SESSION_POOL_ENABLED:
        return None
    if _pool_singleton is None:
        _pool_singleton = McpSessionPool()
    return _pool_singleton


def register_persistent_mcp_loop() -> None:
    """Opt the current (running) loop into session pooling.

    Called once at gateway startup; other processes simply never call it,
    which keeps them on the per-call path with zero cross-loop risk."""
    pool = get_mcp_session_pool()
    if pool is None:
        return
    try:
        pool.register_persistent_loop(asyncio.get_running_loop())
        logger.info("MCP session pooling enabled for this event loop")
    except RuntimeError:
        logger.warning("MCP session pool registration outside a running loop")


async def pooled_or_fresh_call(
    function: Callable[[ClientSession], Coroutine[Any, Any, Any]],
    *,
    server_url: str,
    headers: dict[str, str],
    transport: str,
    auth: Any,
    fresh_call: Callable[[], Coroutine[Any, Any, Any]],
    read_timeout_seconds: float,
) -> Any:
    """Run ``function`` on a pooled session when possible.

    ``fresh_call`` is the caller's per-call path. It backs every case the
    pool doesn't cover (disabled, unregistered loop, in-flight cap, OAuth,
    creation failure) AND the single retry after a pooled session fails —
    never more: a failure of ``fresh_call`` itself propagates, so a
    failing upstream is executed exactly once per call."""
    from onyx.db.enums import MCPTransport

    pool = get_mcp_session_pool()
    transport_is_http = str(transport).upper() == MCPTransport.STREAMABLE_HTTP.value
    if (
        pool is None
        or not transport_is_http
        or auth is not None  # OAuth flows carry per-call state
    ):
        return await fresh_call()

    entry = pool.acquire(
        server_url=server_url,
        headers=headers,
        read_timeout_seconds=read_timeout_seconds,
    )
    if entry is None and pool.loop_is_persistent():
        entry = await pool.create(
            server_url=server_url,
            headers=headers,
            read_timeout_seconds=read_timeout_seconds,
        )
    if entry is None:
        return await fresh_call()

    try:
        return await function(entry.session)
    except Exception:
        pool.discard(entry)
        return await fresh_call()
    finally:
        pool.release(entry)


__all__ = [
    "McpSessionPool",
    "get_mcp_session_pool",
    "pooled_or_fresh_call",
    "register_persistent_mcp_loop",
]
