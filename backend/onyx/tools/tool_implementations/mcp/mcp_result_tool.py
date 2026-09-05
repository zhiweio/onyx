"""Read parts of an MCP result that was too large to inline.

When an MCP tool returns megabytes, the model gets a digest and a handle
instead of the body. This tool is how it reaches back into that body: by dotted
path when it knows what it wants, or by character offset when it needs to read
through the text. Every read is bounded, so following up on a large result
cannot undo the saving the digest just made.
"""

import json
from typing import Any

from onyx.chat.emitter import Emitter
from onyx.configs.app_configs import MCP_RESULT_SLICE_MAX_BYTES
from onyx.db.engine.sql_engine import get_session_with_current_tenant
from onyx.mcp_gateway.digest import extract_path
from onyx.mcp_gateway.handles import has_handle_grant
from onyx.mcp_gateway.storage import load_result
from onyx.server.query_and_chat.placement import Placement
from onyx.server.query_and_chat.streaming_models import (
    CustomToolDelta,
    CustomToolStart,
    Packet,
)
from onyx.tools.interface import Tool
from onyx.tools.models import CustomToolCallSummary, ToolResponse
from onyx.utils.logger import setup_logger

logger = setup_logger()


class MCPResultTool(Tool[None]):
    NAME = "mcp_result"
    DISPLAY_NAME = "MCP Result Reader"
    DESCRIPTION = (
        "Read part of a large MCP tool result that was stored instead of "
        "returned in full. Pass the result_handle from the tool's digest. "
        "Give a json_path to read one field, or an offset to read the raw "
        "text from that position. Reads are capped, so page through long "
        "text by increasing the offset."
    )

    def __init__(self, tool_id: int, emitter: Emitter, user_id: str) -> None:
        super().__init__(emitter=emitter)
        self._id = tool_id
        self._user_id = user_id

    @property
    def id(self) -> int:
        return self._id

    @property
    def name(self) -> str:
        return self.NAME

    @property
    def description(self) -> str:
        return self.DESCRIPTION

    @property
    def display_name(self) -> str:
        return self.DISPLAY_NAME

    def tool_definition(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.NAME,
                "description": self.DESCRIPTION,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "result_handle": {
                            "type": "string",
                            "description": (
                                "The result_handle from a truncated MCP tool response."
                            ),
                        },
                        "json_path": {
                            "type": "string",
                            "description": (
                                "Dotted path into the result, for example "
                                "'structuredContent.items.0.name'. Numeric "
                                "segments index arrays. Omit to read raw text."
                            ),
                        },
                        "offset": {
                            "type": "integer",
                            "description": (
                                "Character offset to start reading from. Defaults to 0."
                            ),
                        },
                        "limit": {
                            "type": "integer",
                            "description": (
                                "Characters to read. Capped by the server."
                            ),
                        },
                    },
                    "required": ["result_handle"],
                },
            },
        }

    def emit_start(self, placement: Placement) -> None:
        self.emitter.emit(
            Packet(placement=placement, obj=CustomToolStart(tool_name=self.NAME))
        )

    def _respond(self, placement: Placement, payload: dict[str, Any]) -> ToolResponse:
        self.emitter.emit(
            Packet(
                placement=placement,
                obj=CustomToolDelta(
                    tool_name=self.NAME, response_type="json", data=payload
                ),
            )
        )
        return ToolResponse(
            rich_response=CustomToolCallSummary(
                tool_name=self.NAME, response_type="json", tool_result=payload
            ),
            llm_facing_response=json.dumps(payload, ensure_ascii=False),
        )

    def run(
        self,
        placement: Placement,
        override_kwargs: None = None,  # noqa: ARG002
        **llm_kwargs: Any,
    ) -> ToolResponse:
        handle = str(llm_kwargs.get("result_handle") or "")
        if not handle:
            return self._respond(placement, {"error": "result_handle is required"})

        # A handle is content-addressed, so it cannot be guessed. The grant
        # check covers the other case: a handle that leaked into a prompt.
        if not has_handle_grant(self._user_id, handle):
            logger.warning(
                "Refused MCP result read for an ungranted handle: %s", handle
            )
            return self._respond(
                placement,
                {
                    "error": (
                        "That result handle is not available in this conversation."
                    )
                },
            )

        with get_session_with_current_tenant() as db_session:
            stored = load_result(db_session, handle)
            db_session.commit()

        if stored is None or stored.payload is None:
            return self._respond(
                placement,
                {
                    "error": (
                        "That result is no longer stored. Call the original tool again."
                    )
                },
            )

        json_path = llm_kwargs.get("json_path")
        if json_path:
            value = extract_path(stored.payload, str(json_path))
            if value is None:
                return self._respond(
                    placement,
                    {
                        "result_handle": handle,
                        "json_path": json_path,
                        "error": "No value at that path.",
                    },
                )
            return self._respond(
                placement,
                self._slice_value(handle, value, llm_kwargs, json_path=str(json_path)),
            )

        return self._respond(
            placement, self._slice_value(handle, stored.payload, llm_kwargs)
        )

    def _slice_value(
        self,
        handle: str,
        value: Any,
        llm_kwargs: dict[str, Any],
        json_path: str | None = None,
    ) -> dict[str, Any]:
        """Return `value` as text, windowed to the requested range."""
        text = (
            value
            if isinstance(value, str)
            else json.dumps(value, ensure_ascii=False, indent=None)
        )

        try:
            offset = max(int(llm_kwargs.get("offset") or 0), 0)
        except (TypeError, ValueError):
            offset = 0
        try:
            requested = int(llm_kwargs.get("limit") or MCP_RESULT_SLICE_MAX_BYTES)
        except (TypeError, ValueError):
            requested = MCP_RESULT_SLICE_MAX_BYTES
        limit = max(min(requested, MCP_RESULT_SLICE_MAX_BYTES), 1)

        window = text[offset : offset + limit]
        next_offset = offset + len(window)
        payload: dict[str, Any] = {
            "result_handle": handle,
            "offset": offset,
            "returned_chars": len(window),
            "total_chars": len(text),
            "content": window,
        }
        if json_path:
            payload["json_path"] = json_path
        if next_offset < len(text):
            payload["next_offset"] = next_offset
        return payload
