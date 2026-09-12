from collections.abc import Coroutine
from typing import Any
from unittest.mock import MagicMock

import pytest
from mcp import ClientSession
from mcp.types import CallToolResult

from onyx.server.features.mcp import client
from onyx.server.features.mcp.oauth import MCPReauthenticationRequired


def test_unwrap_exception_group_returns_inner_runtime_error() -> None:
    inner = RuntimeError("Invalid structured content returned by tool x")
    error = ExceptionGroup(
        "unhandled errors in a TaskGroup",
        [ExceptionGroup("unhandled errors in a TaskGroup", [inner])],
    )
    assert client.unwrap_exception_group(error) is inner


def test_sync_client_unwraps_nested_reauthentication_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reauthentication_required = MCPReauthenticationRequired()

    def raise_nested_error(coroutine: Coroutine[Any, Any, object]) -> object:
        coroutine.close()
        raise ExceptionGroup(
            "transport cleanup",
            [ExceptionGroup("request failed", [reauthentication_required])],
        )

    async def operation(_session: ClientSession) -> None:
        raise AssertionError("transport should fail before opening a session")

    monkeypatch.setattr(client, "run_async_sync_no_cancel", raise_nested_error)

    with pytest.raises(MCPReauthenticationRequired) as exc_info:
        client._call_mcp_client_function_sync(
            operation,
            "https://mcp.example.com/mcp",
        )

    assert exc_info.value is reauthentication_required


@pytest.mark.asyncio
async def test_async_client_unwraps_task_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inner = RuntimeError("Invalid structured content returned by tool x")

    async def raise_group() -> object:
        raise ExceptionGroup(
            "unhandled errors in a TaskGroup",
            [ExceptionGroup("unhandled errors in a TaskGroup", [inner])],
        )

    monkeypatch.setattr(
        client,
        "_create_mcp_client_function_runner",
        lambda *args, **kwargs: raise_group,
    )

    async def operation(_session: ClientSession) -> None:
        raise AssertionError("runner should fail before opening a session")

    with pytest.raises(RuntimeError, match="Invalid structured content") as exc_info:
        await client._call_mcp_client_function_async(
            operation,
            "https://mcp.example.com/mcp",
        )

    assert exc_info.value is inner


@pytest.mark.asyncio
async def test_soft_validate_keeps_payload_when_schema_rejects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def reject(
        _session: ClientSession, _name: str, _result: object
    ) -> None:
        raise RuntimeError("None is not of type 'string'")

    monkeypatch.setattr(ClientSession, "_validate_tool_result", reject)
    await client._soft_validate_tool_result(
        MagicMock(spec=ClientSession),
        "get_a_share_financials_indicators",
        MagicMock(spec=CallToolResult),
    )
