from mcp.types import CallToolResult, TextContent

from onyx.mcp_gateway.protocol import call_result_from_payload


def test_call_result_keeps_structured_content() -> None:
    payload = {
        "content": [{"type": "text", "text": "ok"}],
        "structuredContent": {"name": "Acme", "total": 1},
        "isError": False,
    }
    result = call_result_from_payload(payload)
    assert isinstance(result, CallToolResult)
    assert result.structuredContent == {"name": "Acme", "total": 1}
    assert result.content == [TextContent(type="text", text="ok")]
    assert result.isError is False


def test_call_result_rebuilds_from_structured_content_alone() -> None:
    payload = {
        "content": [],
        "structuredContent": {"items": [1, 2]},
        "isError": False,
    }
    result = call_result_from_payload(payload)
    assert result.structuredContent == {"items": [1, 2]}
    assert result.content == []
