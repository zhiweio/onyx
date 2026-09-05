import json
from typing import Any

from onyx.configs.app_configs import (
    PATSNAP_MCP_NAME_FRAGMENT,
    PATSNAP_MCP_TOOL,
    QIXINBAO_MCP_NAME_FRAGMENT,
    QIXINBAO_MCP_TOOL,
)
from onyx.db.engine.sql_engine import get_session_with_current_tenant
from onyx.db.enums import MCPTransport
from onyx.db.mcp import find_mcp_server_by_name_fragment
from onyx.db.models import MCPServer
from onyx.server.features.mcp.client import call_mcp_tool
from onyx.server.features.mcp.credentials import extract_connection_data
from onyx.tax.models import (
    AccessMode,
    CompanyEntity,
    LiveQuery,
    NormalizedRecord,
    PatentEntity,
    PluginStatus,
    SourceDomain,
    SourceHit,
    TrustTier,
)
from onyx.utils.logger import setup_logger

logger = setup_logger()


def _admin_headers(server: MCPServer) -> dict[str, str]:
    config = server.admin_connection_config
    if config is None:
        return {}
    data = extract_connection_data(config, apply_mask=False)
    headers = data.get("headers")
    if isinstance(headers, dict):
        return {str(key): str(value) for key, value in headers.items()}
    return {}


def _parse_hits(source_id: str, raw: str, limit: int) -> list[SourceHit]:
    try:
        payload: Any = json.loads(raw)
    except json.JSONDecodeError:
        return [
            SourceHit(
                source_id=source_id,
                hit_id=f"{source_id}:raw",
                title="MCP result",
                url="",
                snippet=raw[:800],
            )
        ]
    items: list[Any]
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        for key in ("results", "items", "data", "records"):
            value = payload.get(key)
            if isinstance(value, list):
                items = value
                break
        else:
            items = [payload]
    else:
        items = []
    hits: list[SourceHit] = []
    for index, item in enumerate(items[:limit]):
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or item.get("link") or "")
        title = str(item.get("title") or item.get("name") or f"{source_id} {index}")
        snippet = str(item.get("snippet") or item.get("summary") or "")
        hits.append(
            SourceHit(
                source_id=source_id,
                hit_id=str(item.get("id") or url or f"{source_id}:{index}"),
                title=title,
                url=url,
                snippet=snippet[:800],
            )
        )
    return hits


class McpSourcePlugin:
    source_id: str
    display_name: str
    domain: SourceDomain
    trust_tier: TrustTier
    access_mode: AccessMode = AccessMode.MCP
    name_fragment: str
    tool_name: str | None

    def _server(self) -> MCPServer | None:
        with get_session_with_current_tenant() as db_session:
            return find_mcp_server_by_name_fragment(db_session, self.name_fragment)

    def healthcheck(self) -> PluginStatus:
        try:
            server = self._server()
        except Exception as exc:
            return PluginStatus(ok=False, configured=False, message=str(exc))
        if server is None:
            return PluginStatus(
                ok=False,
                configured=False,
                message=f"No MCP server name matches '{self.name_fragment}'.",
            )
        return PluginStatus(ok=True, configured=True, message=server.name)

    def search(self, query: LiveQuery) -> list[SourceHit]:
        server = self._server()
        if server is None:
            return []
        tool_name = self.tool_name or "search"
        arguments: dict[str, Any] = {
            "query": query.query,
            "company": query.company,
            "uscc": query.uscc,
            "patent_keyword": query.patent_keyword,
        }
        try:
            raw = call_mcp_tool(
                server.server_url,
                tool_name,
                {key: value for key, value in arguments.items() if value},
                connection_headers=_admin_headers(server),
                transport=server.transport or MCPTransport.STREAMABLE_HTTP,
            )
        except Exception:
            logger.warning(
                "MCP search failed for %s tool=%s",
                self.source_id,
                tool_name,
                exc_info=True,
            )
            return []
        return _parse_hits(self.source_id, raw, query.limit)

    def fetch(self, hit: SourceHit) -> NormalizedRecord | None:
        company = None
        patent = None
        if self.domain == SourceDomain.COMMERCIAL:
            company = CompanyEntity(name=hit.title)
        if self.domain == SourceDomain.IP:
            patent = PatentEntity(assignee=hit.title)
        return NormalizedRecord(
            source_id=self.source_id,
            record_id=hit.hit_id,
            url=hit.url,
            title=hit.title,
            trust_tier=self.trust_tier,
            domain=self.domain,
            company=company,
            patent=patent,
            snippet=hit.snippet,
            full_text=hit.snippet,
        )


class QixinbaoMcpPlugin(McpSourcePlugin):
    source_id = "qixinbao_mcp"
    display_name = "启信宝 MCP"
    domain = SourceDomain.COMMERCIAL
    trust_tier = TrustTier.COMMERCIAL
    name_fragment = QIXINBAO_MCP_NAME_FRAGMENT
    tool_name = QIXINBAO_MCP_TOOL


class PatsnapMcpPlugin(McpSourcePlugin):
    source_id = "patsnap_mcp"
    display_name = "智慧芽 MCP"
    domain = SourceDomain.IP
    trust_tier = TrustTier.COMMERCIAL
    name_fragment = PATSNAP_MCP_NAME_FRAGMENT
    tool_name = PATSNAP_MCP_TOOL
