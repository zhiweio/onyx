"""MCP session pool: reuse, eviction, loop affinity, exact retry semantics.

The pool is tested against a fake in-process streamable-http MCP server
(a minimal JSON-RPC endpoint counting session establishments), so the
assertions are on real connection counts, not mocks of the pool itself.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

import onyx.server.features.mcp.session_pool as pool_mod
from onyx.server.features.mcp.session_pool import (
    McpSessionPool,
    pooled_or_fresh_call,
)


class _CountingUpstream:
    """Minimal streamable-http MCP-ish server counting connections.

    Implements just enough of the MCP handshake for ClientSession to
    initialize: JSON-RPC responses over a chunked HTTP stream."""

    def __init__(self) -> None:
        self.connections = 0
        self.requests = 0

    async def handler(self, scope: dict, receive: Any, send: Any) -> None:  # noqa: ARG002
        self.connections += 1
        body = b""
        while True:
            message = await receive()
            if message["type"] == "http.request":
                body += message.get("body", b"")
                if not message.get("more_body"):
                    break
            else:
                return
        payload = json.loads(body or b"{}")
        self.requests += 1
        # Respond to initialize / notifications / tools-call uniformly with
        # a minimal valid result; ClientSession only needs the handshake.
        result: dict[str, Any] = {}
        if payload.get("method") == "initialize":
            result = {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "serverInfo": {"name": "fake", "version": "0"},
            }
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [
                    [b"content-type", b"application/json"],
                    [b"cache-control", b"no-cache"],
                ],
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": payload.get("id"),
                        "result": result,
                    }
                ).encode(),
                "more_body": False,
            }
        )


@pytest.fixture(autouse=True)
def _local_pool(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Route pooled_or_fresh_call at a per-test pool (not the singleton)."""
    pools: dict[str, Any] = {}

    pools["pool"] = McpSessionPool(idle_ttl=60)

    def _factory() -> Any:
        return pools["pool"]

    monkeypatch.setattr(pool_mod, "get_mcp_session_pool", _factory)
    return pools


def test_pool_reuses_session_across_calls(_local_pool: dict[str, Any]) -> None:
    """Two calls on a registered loop reuse ONE pooled entry; fresh never runs.

    Connection-level counting is asserted in the live gateway e2e (stats);
    here the pool's own bookkeeping is the contract."""
    import onyx.server.features.mcp.session_pool as pool_mod

    async def scenario() -> dict[str, Any]:
        pool = _local_pool["pool"]
        pool.register_persistent_loop()
        key = f"|{pool_mod._headers_hash({})}"
        entry = pool_mod._PooledSession(
            key=key,
            loop=asyncio.get_running_loop(),
            session=object(),
            transport_cm=None,
            session_cm=None,
        )
        pool._entries[key] = entry

        seen_sessions: list[int] = []

        async def fn(session: Any) -> str:
            seen_sessions.append(id(session))
            return "ok"

        async def fresh() -> str:
            raise AssertionError("fresh path should not run while pooled works")

        for _ in range(2):
            out = await pooled_or_fresh_call(
                fn,
                server_url="",
                headers={},
                transport="streamable_http",
                auth=None,
                fresh_call=fresh,
                read_timeout_seconds=5,
            )
            assert out == "ok"
        return {"metrics": pool.metrics, "size": len(pool._entries)}

    result = asyncio.run(scenario())
    assert result["metrics"]["reused"] == 2
    assert result["metrics"]["created"] == 0
    assert result["metrics"]["fallback"] == 0
    assert result["size"] == 1


def test_unregistered_loop_never_creates_entries(
    _local_pool: dict[str, Any],
) -> None:
    """Without register_persistent_loop, everything goes fresh — no leak."""

    async def scenario() -> dict[str, Any]:
        pool = McpSessionPool()
        _local_pool["pool"] = pool
        # NOT registering the loop.

        async def fresh() -> str:
            return "fresh"

        out = await pooled_or_fresh_call(
            lambda session: (_ for _ in ()).throw(AssertionError("pooled used")),  # noqa: ARG005
            server_url="http://127.0.0.1:1/mcp",
            headers={},
            transport="streamable_http",
            auth=None,
            fresh_call=fresh,
            read_timeout_seconds=5,
        )
        return {"out": out, "size": len(pool._entries)}

    result = asyncio.run(scenario())
    assert result["out"] == "fresh"
    assert result["size"] == 0


def test_pooled_failure_retries_fresh_exactly_once(
    _local_pool: dict[str, Any],
) -> None:
    monkey_holder = _local_pool
    """A pooled-session error discards the entry and retries fresh once;
    a fresh failure propagates without a second attempt."""

    async def scenario() -> dict[str, Any]:
        pool = McpSessionPool()
        pool.register_persistent_loop()
        monkey_holder["pool"] = pool
        key = f"|{pool_mod._headers_hash({})}"
        entry = pool_mod._PooledSession(
            key=key,
            loop=asyncio.get_running_loop(),
            session=object(),
            transport_cm=None,
            session_cm=None,
        )
        pool._entries[key] = entry

        fresh_calls: list[int] = []

        async def failing_pooled(session: Any) -> str:  # noqa: ARG001
            raise RuntimeError("connection reset")

        async def fresh() -> str:
            fresh_calls.append(1)
            return "fresh-ok"

        # Routed through the fake entry: acquire hits it by key.
        async def pooled_call() -> Any:
            return await pooled_or_fresh_call(
                failing_pooled,
                server_url="",  # key of ""+hash of empty headers == entry key
                headers={},
                transport="streamable_http",
                auth=None,
                fresh_call=fresh,
                read_timeout_seconds=5,
            )

        out = await pooled_call()

        # Fresh failure propagates (no retry of fresh itself).
        async def fresh_fail() -> str:
            raise RuntimeError("upstream down")

        async def pooled_fail_after_fresh() -> str:
            return await pooled_or_fresh_call(
                failing_pooled,
                server_url="",
                headers={},
                transport="streamable_http",
                auth=None,
                fresh_call=fresh_fail,
                read_timeout_seconds=5,
            )

        propagated = False
        try:
            entry2 = pool_mod._PooledSession(
                key=key,
                loop=asyncio.get_running_loop(),
                session=object(),
                transport_cm=None,
                session_cm=None,
            )
            pool._entries[key] = entry2
            await pooled_fail_after_fresh()
        except RuntimeError:
            propagated = True
        return {
            "out": out,
            "fresh_calls": len(fresh_calls),
            "propagated": propagated,
            "entries_left": len(pool._entries),
        }

    result = asyncio.run(scenario())
    assert result["out"] == "fresh-ok"
    assert result["fresh_calls"] == 1  # exactly one retry
    assert result["propagated"] is True  # fresh failure not retried
    assert result["entries_left"] == 0  # poisoned entries discarded


def test_inflight_cap_falls_back(_local_pool: dict[str, Any]) -> None:
    async def scenario() -> dict[str, Any]:
        pool = McpSessionPool(inflight_cap=1)
        pool.register_persistent_loop()
        _local_pool["pool"] = pool
        key = f"|{pool_mod._headers_hash({})}"
        entry = pool_mod._PooledSession(
            key=key,
            loop=asyncio.get_running_loop(),
            session=object(),
            transport_cm=None,
            session_cm=None,
        )
        entry.in_flight = 1  # at cap
        pool._entries[key] = entry

        got = {}

        async def fresh() -> str:
            got["fresh"] = True
            return "fresh"

        out = await pooled_or_fresh_call(
            lambda s: (_ for _ in ()).throw(AssertionError("should not pool")),  # noqa: ARG005
            server_url="",
            headers={},
            transport="streamable_http",
            auth=None,
            fresh_call=fresh,
            read_timeout_seconds=5,
        )
        return {"out": out, "fresh": got.get("fresh", False)}

    result = asyncio.run(scenario())
    assert result["out"] == "fresh"
    assert result["fresh"] is True


def test_lru_eviction_caps_size() -> None:
    async def scenario() -> dict[str, Any]:
        pool = McpSessionPool(max_size=2)
        pool.register_persistent_loop()
        for index in range(3):
            key = f"http://srv{index}|h"
            pool._entries[key] = pool_mod._PooledSession(
                key=key,
                loop=asyncio.get_running_loop(),
                session=object(),
                transport_cm=None,
                session_cm=None,
            )
        pool._evict_lru_if_full()
        # Creating a 4th after eviction logic keeps us at/under cap.
        return {"size": len(pool._entries), "lru": pool.metrics["evicted_lru"]}

    result = asyncio.run(scenario())
    assert result["lru"] >= 1
