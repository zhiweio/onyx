import json
import time
from typing import Any

from mcp.client.auth import OAuthClientProvider
from mcp.types import CallToolResult

from onyx.chat.emitter import Emitter
from onyx.db.engine.sql_engine import get_session_with_current_tenant
from onyx.db.enums import MCPAuthenticationType, MCPTransport
from onyx.db.models import MCPConnectionConfig, MCPServer
from onyx.mcp_gateway.handles import grant_handle
from onyx.mcp_gateway.models import CachePolicySpec
from onyx.mcp_gateway.storage import canonical_bytes, store_result
from onyx.server.features.mcp.client import call_mcp_tool_raw, process_mcp_result
from onyx.server.features.mcp.credentials import ResolvedMCPCredentials
from onyx.server.features.mcp.models import (
    DENYLISTED_MCP_HEADERS,
    merge_mcp_headers,
)
from onyx.server.features.mcp.oauth import (
    MCPReauthenticationRequired,
    make_oauth_provider,
    refresh_mcp_oauth_token_if_expired,
)
from onyx.server.metrics.mcp_client import record_mcp_client_tool_outcome
from onyx.server.metrics.mcp_common import MCPToolCallStatus
from onyx.server.query_and_chat.placement import Placement
from onyx.server.query_and_chat.streaming_models import (
    CustomToolDelta,
    CustomToolStart,
    Packet,
)
from onyx.tools.interface import Tool
from onyx.tools.models import CustomToolCallSummary, ToolResponse
from onyx.tools.tool_implementations.utils import truncate_output
from onyx.tools.tool_name import sanitize_tool_name
from onyx.utils.logger import setup_logger

logger = setup_logger()

_AUTH_ERROR_INDICATORS = (
    "401",
    "unauthorized",
    "authentication",
    "forbidden",
    "access denied",
    "invalid token",
    "invalid api key",
    "invalid credentials",
    "please reconnect to the server",
)

# TODO: for now we're fitting MCP tool responses into the CustomToolCallSummary class
# In the future we may want custom handling for MCP tool responses
# class MCPToolCallSummary(BaseModel):
#     tool_name: str
#     server_url: str
#     tool_result: Any
#     server_name: str


def _normalize_parameters_schema(schema: dict[str, Any] | None) -> dict[str, Any]:
    # Azure OpenAI rejects object schemas that omit `properties` with
    # "object schema missing properties". MCP servers (e.g. AWS Knowledge MCP's
    # aws___list_regions) may legally return `{"type": "object"}` with no
    # properties for zero-arg tools, so seed `properties: {}` ourselves.
    if not schema:
        return {"type": "object", "properties": {}}
    if schema.get("type", "object") == "object" and "properties" not in schema:
        return {**schema, "type": "object", "properties": {}}
    return schema


class MCPTool(Tool[None]):
    """Tool implementation for MCP (Model Context Protocol) servers"""

    def __init__(
        self,
        tool_id: int,
        emitter: Emitter,
        mcp_server: MCPServer,  # TODO: these should be basemodels instead of db objects
        tool_name: str,
        tool_description: str,
        tool_definition: dict[str, Any],
        connection_config: MCPConnectionConfig | None = None,
        user_email: str = "",
        user_id: str = "",
        user_oauth_token: str | None = None,
        additional_headers: dict[str, str] | None = None,
        resolved_credentials: ResolvedMCPCredentials | None = None,
        result_policy: CachePolicySpec | None = None,
    ) -> None:
        super().__init__(emitter=emitter)

        self._id = tool_id
        self.mcp_server = mcp_server
        self.connection_config = connection_config
        self.user_email = user_email
        self._user_id = user_id
        self._user_oauth_token = user_oauth_token
        self._additional_headers = additional_headers or {}
        self._resolved_credentials = resolved_credentials
        # Controls the inline/spill threshold and the digest shape. System
        # servers pass their catalog policy so pack-declared digest paths
        # apply; everything else uses the deployment defaults.
        self._result_policy = result_policy or CachePolicySpec()

        self._mcp_tool_name = tool_name
        self._name = tool_name  # NOTE: this may change in _disambiguate_mcp_tool_names
        self._tool_definition = tool_definition
        self._description = tool_description
        self._display_name = tool_definition.get("displayName", tool_name)
        self._llm_name = sanitize_tool_name(f"mcp_{mcp_server.name}_{tool_name}")

    @property
    def id(self) -> int:
        return self._id

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def display_name(self) -> str:
        return self._display_name

    def use_disambiguated_name(self) -> None:
        self._name = self._llm_name

    def tool_definition(self) -> dict:
        """Return the tool definition from the MCP server"""
        # Convert MCP tool definition to OpenAI function calling format
        return {
            "type": "function",
            "function": {
                "name": self._name,
                "description": self._description,
                "parameters": _normalize_parameters_schema(self._tool_definition),
            },
        }

    def emit_start(self, placement: Placement) -> None:
        self.emitter.emit(
            Packet(
                placement=placement,
                obj=CustomToolStart(tool_name=self._name),
            )
        )

    def _build_response(
        self, placement: Placement, raw_result: CallToolResult
    ) -> ToolResponse:
        """Turn a tool result into a response, spilling it if it is large.

        MCP servers routinely answer with megabytes. Below the inline threshold
        nothing changes: the flattened text goes straight to the model. Above
        it, the body is persisted and the model gets a digest plus a handle it
        can read through the `mcp_result` tool, which keeps one answer from
        consuming the whole context window.
        """
        payload = raw_result.model_dump(mode="json")
        size_bytes = len(canonical_bytes(payload))

        if size_bytes <= self._result_policy.inline_threshold_bytes:
            tool_result_dict = {"tool_result": process_mcp_result(raw_result)}
            self.emitter.emit(
                Packet(
                    placement=placement,
                    obj=CustomToolDelta(
                        tool_name=self._name,
                        response_type="json",
                        data=tool_result_dict,
                    ),
                )
            )
            return ToolResponse(
                rich_response=CustomToolCallSummary(
                    tool_name=self._name,
                    response_type="json",
                    tool_result=tool_result_dict,
                ),
                llm_facing_response=json.dumps(tool_result_dict),
            )

        stored = None
        try:
            with get_session_with_current_tenant() as db_session:
                stored = store_result(
                    db_session,
                    payload,
                    self._result_policy,
                    tool_name=self._mcp_tool_name,
                )
                db_session.commit()
        except Exception:
            logger.exception(
                "Could not persist the large result of MCP tool '%s'", self._name
            )

        if stored is None:
            # Either past the hard ceiling or storage failed. Truncating beats
            # both dropping the answer and blowing up the context window.
            truncated = truncate_output(
                process_mcp_result(raw_result),
                self._result_policy.inline_threshold_bytes,
                label=f"{self._name} output",
            )
            tool_result_dict = {"tool_result": truncated, "truncated": True}
            self.emitter.emit(
                Packet(
                    placement=placement,
                    obj=CustomToolDelta(
                        tool_name=self._name,
                        response_type="json",
                        data=tool_result_dict,
                    ),
                )
            )
            return ToolResponse(
                rich_response=CustomToolCallSummary(
                    tool_name=self._name,
                    response_type="json",
                    tool_result=tool_result_dict,
                ),
                llm_facing_response=json.dumps(tool_result_dict),
            )

        grant_handle(self._user_id, stored.blob_id)

        llm_payload = {
            "tool_result_digest": stored.digest,
            "result_handle": stored.blob_id,
            "total_bytes": stored.size_bytes,
            "truncated": True,
            "hint": (
                "The full result was too large for the conversation. Call "
                "mcp_result with this result_handle to read a field by path or "
                "a slice of the raw text."
            ),
        }
        self.emitter.emit(
            Packet(
                placement=placement,
                obj=CustomToolDelta(
                    tool_name=self._name,
                    response_type="json",
                    data=llm_payload,
                    file_ids=[stored.file_id] if stored.file_id else None,
                ),
            )
        )
        return ToolResponse(
            rich_response=CustomToolCallSummary(
                tool_name=self._name,
                response_type="json",
                tool_result=llm_payload,
            ),
            llm_facing_response=json.dumps(llm_payload),
        )

    def run(
        self,
        placement: Placement,
        override_kwargs: None = None,  # noqa: ARG002
        **llm_kwargs: Any,
    ) -> ToolResponse:
        """Execute the MCP tool by calling the MCP server"""
        _start = time.monotonic()
        _server = self.mcp_server.name
        outcome = MCPToolCallStatus.ERROR
        try:
            request_headers = {
                name: value
                for name, value in self._additional_headers.items()
                if name.lower() not in DENYLISTED_MCP_HEADERS
            }
            if denylisted := sorted(
                set(self._additional_headers) - set(request_headers)
            ):
                logger.warning(
                    "MCP tool '%s' received denylisted headers that were filtered: %s",
                    self._name,
                    denylisted,
                )
            credentials = self._resolved_credentials or ResolvedMCPCredentials(
                connection_config=self.connection_config,
                user_oauth_token=self._user_oauth_token,
                auth_type=self.mcp_server.auth_type,
                user_email=self.user_email,
            )
            headers = merge_mcp_headers(
                request_headers,
                credentials.build_headers(),
            )

            # Extra request headers can stand in for missing credentials, but
            # not for a dead OAuth grant — its stale bearer wins the header
            # merge, so the call can only fail upstream.
            if not credentials.can_authenticate() and (
                credentials.needs_reauth() or not self._additional_headers
            ):
                auth_error_msg = (
                    f"The {self._name} tool from {self.mcp_server.name} requires "
                    "connection values. Tell the user to connect to the server "
                    "from the MCP dropdown before using this tool."
                )
                logger.warning(
                    "Authentication required for MCP tool '%s' but no credentials found",
                    self._name,
                )

                error_result = {"error": auth_error_msg}
                llm_facing_response = json.dumps(error_result)

                # Emit CustomToolDelta packet
                self.emitter.emit(
                    Packet(
                        placement=placement,
                        obj=CustomToolDelta(
                            tool_name=self._name,
                            response_type="json",
                            data=error_result,
                        ),
                    )
                )

                outcome = MCPToolCallStatus.AUTH_ERROR
                return ToolResponse(
                    rich_response=CustomToolCallSummary(
                        tool_name=self._name,
                        response_type="json",
                        tool_result=error_result,
                    ),
                    llm_facing_response=llm_facing_response,
                )

            # For OAuth servers, construct OAuthClientProvider so the MCP SDK
            # can refresh expired tokens automatically
            auth: OAuthClientProvider | None = None
            if (
                self.mcp_server.auth_type == MCPAuthenticationType.OAUTH
                and self.connection_config is not None
                and self._user_id
            ):
                if self.mcp_server.transport == MCPTransport.SSE:
                    # httpx.Auth refresh can't run over an open SSE stream;
                    # refresh proactively here instead. Non-fatal on failure.
                    try:
                        refreshed_header = refresh_mcp_oauth_token_if_expired(
                            self.mcp_server,
                            self.connection_config.id,
                        )
                        if refreshed_header:
                            headers["Authorization"] = refreshed_header
                    except Exception:
                        logger.exception(
                            "MCP tool '%s': proactive SSE OAuth token refresh failed; using existing token",
                            self._name,
                        )
                else:
                    auth = make_oauth_provider(
                        self.mcp_server,
                        self.connection_config.id,
                        None,
                    )

            raw_result = call_mcp_tool_raw(
                self.mcp_server.server_url,
                self._mcp_tool_name,
                llm_kwargs,
                connection_headers=headers,
                transport=self.mcp_server.transport or MCPTransport.STREAMABLE_HTTP,
                auth=auth,
            )

            logger.info("MCP tool '%s' executed successfully", self._name)

            response = self._build_response(placement, raw_result)
            outcome = MCPToolCallStatus.SUCCESS
            return response

        except Exception as e:
            error_str = str(e).lower()
            logger.error("Failed to execute MCP tool '%s': %s", self._name, e)

            is_auth_error = isinstance(e, MCPReauthenticationRequired) or any(
                indicator in error_str for indicator in _AUTH_ERROR_INDICATORS
            )

            if is_auth_error:
                outcome = MCPToolCallStatus.AUTH_ERROR
                auth_error_msg = (
                    f"Authentication failed for the {self._name} tool from {self.mcp_server.name}. "
                    f"Please use the MCP dropdown in the chat bar to update your credentials "
                    f"for the {self.mcp_server.name} server. Original error: {str(e)}"
                )
                error_result = {"error": auth_error_msg}
            else:
                error_result = {"error": f"Tool execution failed: {str(e)}"}

            llm_facing_response = json.dumps(error_result)

            # Emit CustomToolDelta packet
            self.emitter.emit(
                Packet(
                    placement=placement,
                    obj=CustomToolDelta(
                        tool_name=self._name,
                        response_type="json",
                        data=error_result,
                    ),
                )
            )

            return ToolResponse(
                rich_response=CustomToolCallSummary(
                    tool_name=self._name,
                    response_type="json",
                    tool_result=error_result,
                ),
                llm_facing_response=llm_facing_response,
            )
        finally:
            record_mcp_client_tool_outcome(
                server_name=_server,
                tool_name=self._name,
                start_time=_start,
                status=outcome,
            )
