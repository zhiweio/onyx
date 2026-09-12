from typing import Any

import pytest

from onyx.db.enums import MCPTransport
from onyx.mcp_gateway.upstream import UpstreamTarget, call_upstream


@pytest.mark.asyncio
async def test_call_upstream_returns_inner_error_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail(*_args: Any, **_kwargs: Any) -> object:
        raise ExceptionGroup(
            "unhandled errors in a TaskGroup",
            [
                ExceptionGroup(
                    "unhandled errors in a TaskGroup",
                    [RuntimeError("None is not of type 'string'")],
                )
            ],
        )

    monkeypatch.setattr(
        "onyx.mcp_gateway.upstream.call_mcp_tool_raw_async",
        fail,
    )
    payload = await call_upstream(
        UpstreamTarget(
            url="https://example.com/mcp",
            headers={},
            transport=MCPTransport.STREAMABLE_HTTP,
        ),
        "get_a_share_financials_indicators",
        {"thscode": "603617.SH", "report": "2023-4"},
    )
    assert payload["isError"] is True
    assert payload["content"][0]["text"] == "None is not of type 'string'"
