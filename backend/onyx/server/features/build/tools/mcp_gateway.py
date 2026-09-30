"""Enterprise MCP gateway: server-side MCP client with allowlist + audit.

Sandbox agents reach external MCP servers (invoice checks, business
registry, pharma databases) through the platform, never directly:

- servers are configured deployment-wide (``MCP_GATEWAY_SERVERS``, a
  JSON list of {name, url, headers}); credentials come from the
  encrypted env-var store in a follow-up
- every call is allowlisted by server name (scenario bindings feed this)
- every call is journaled (who, server, tool, ok) for audit

Connections use the MCP SDK's streamable-http client, one short-lived
session per call — stateless and simple; pooling is a later
optimization.
"""

from __future__ import annotations

import json
import os

from dataclasses import dataclass, field
from typing import Any, Callable

from onyx.utils.logger import setup_logger

logger = setup_logger()

_GATEWAY_SERVERS_ENV = "MCP_GATEWAY_SERVERS"


class McpGatewayError(Exception):
    """Gateway refused or the upstream call failed; message is safe to show."""


@dataclass(frozen=True)
class GatewayServerConfig:
    name: str
    url: str
    headers: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class GatewayCall:
    server: str
    tool: str
    arguments: dict[str, Any]
    user_id: str
    ok: bool
    error: str | None = None


AuditFn = Callable[[GatewayCall], None]


def load_gateway_servers(
    raw: str | None = None,
) -> dict[str, GatewayServerConfig]:
    """Parse the gateway server config (env JSON or injected raw string)."""
    if raw is None:
        raw = os.environ.get(_GATEWAY_SERVERS_ENV, "")
    raw = (raw or "").strip()
    if not raw:
        return {}
    try:
        entries = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise McpGatewayError(f"{_GATEWAY_SERVERS_ENV} is not valid JSON: {exc}")
    servers: dict[str, GatewayServerConfig] = {}
    for entry in entries:
        if not isinstance(entry, dict) or not entry.get("name") or not entry.get("url"):
            continue
        headers = {
            str(k): str(v) for k, v in (entry.get("headers") or {}).items()
        }
        config = GatewayServerConfig(
            name=str(entry["name"]), url=str(entry["url"]), headers=headers
        )
        servers[config.name] = config
    return servers


class McpGatewayService:
    """Stateless MCP client fan-out with allowlist and audit."""

    def __init__(
        self,
        servers: dict[str, GatewayServerConfig],
        *,
        audit: AuditFn | None = None,
    ) -> None:
        self._servers = servers
        self._audit = audit

    @property
    def servers(self) -> dict[str, GatewayServerConfig]:
        return self._servers

    def _check_allowed(self, server: str, allowed: set[str] | None) -> GatewayServerConfig:
        config = self._servers.get(server)
        if config is None:
            raise McpGatewayError(
                f"unknown MCP gateway server {server!r}; "
                f"configured: {sorted(self._servers)}"
            )
        if allowed is not None and server not in allowed:
            raise McpGatewayError(
                f"MCP server {server!r} is not granted for this task"
            )
        return config

    async def call_tool(
        self,
        *,
        server: str,
        tool: str,
        arguments: dict[str, Any],
        user_id: str,
        allowed_servers: set[str] | None = None,
    ) -> str:
        config = self._check_allowed(server, allowed_servers)
        try:
            result = await self._call_upstream(config, tool, arguments)
            self._record(GatewayCall(server, tool, arguments, user_id, ok=True))
            return result
        except Exception as exc:
            self._record(
                GatewayCall(server, tool, arguments, user_id, ok=False, error=str(exc))
            )
            raise

    async def _call_upstream(
        self, config: GatewayServerConfig, tool: str, arguments: dict[str, Any]
    ) -> str:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client

        async with streamablehttp_client(config.url, headers=config.headers) as (
            read,
            write,
            _,
        ):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool, arguments)
        return _render_result(result)

    def _record(self, call: GatewayCall) -> None:
        if self._audit is None:
            return
        try:
            self._audit(call)
        except Exception:
            logger.exception("MCP gateway audit write failed")

    def call_tool_sync(
        self,
        *,
        server: str,
        tool: str,
        arguments: dict[str, Any],
        user_id: str,
        allowed_servers: set[str] | None = None,
    ) -> str:
        """Sync wrapper for the bridge's sync tool endpoints (threadpool)."""
        import asyncio

        return asyncio.run(
            self.call_tool(
                server=server,
                tool=tool,
                arguments=arguments,
                user_id=user_id,
                allowed_servers=allowed_servers,
            )
        )


def _render_result(result: Any) -> str:
    """Flatten an SDK CallToolResult into readable text blocks."""
    parts: list[str] = []
    content = getattr(result, "content", None) or []
    for block in content:
        text = getattr(block, "text", None)
        if text:
            parts.append(str(text))
    if getattr(result, "isError", False):
        joined = "\n".join(parts) or "tool error"
        raise McpGatewayError(f"MCP tool error: {joined}")
    return "\n".join(parts) if parts else "(no content)"


def default_gateway_servers() -> McpGatewayService:
    """The deployment gateway from env config. Calls fail with a clear
    'unknown server' message when nothing is configured."""
    return McpGatewayService(load_gateway_servers())
