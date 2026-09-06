from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from onyx.db.enums import MCPGatewayAuthAdapter
from onyx.db.models import MCPCatalogEntry
from onyx.utils.sensitive import SensitiveValue


def entry_credentials(entry: MCPCatalogEntry) -> dict[str, Any]:
    raw = entry.credentials
    if isinstance(raw, SensitiveValue):
        value = raw.get_value(apply_mask=False)
        return value if isinstance(value, dict) else {}
    return raw if isinstance(raw, dict) else {}


def apply_auth(entry: MCPCatalogEntry) -> tuple[str, dict[str, str]]:
    """Return (upstream_url, headers) for a system MCP server.

    These are the shared credentials the admin configured. They never leave the
    backend: users reach the upstream through the gateway, which attaches them
    here.
    """
    creds = entry_credentials(entry)
    url = entry.upstream_url
    headers: dict[str, str] = {}

    extra = creds.get("extra_headers")
    if isinstance(extra, dict):
        headers.update({str(key): str(value) for key, value in extra.items()})

    adapter = entry.auth_adapter
    token = str(creds.get("api_key") or creds.get("authorization") or "")
    if adapter == MCPGatewayAuthAdapter.BEARER and token:
        headers["Authorization"] = f"Bearer {token}"
    elif adapter == MCPGatewayAuthAdapter.RAW_AUTHORIZATION and token:
        headers["Authorization"] = token
    elif adapter == MCPGatewayAuthAdapter.QUERY_APIKEY and token:
        url = _append_query(url, {"apikey": token})
    elif adapter == MCPGatewayAuthAdapter.HEADER_MAP:
        # Everything the upstream needs is already in extra_headers.
        pass
    return url, headers


def _append_query(url: str, params: dict[str, str]) -> str:
    parsed = urlparse(url)
    current = dict(parse_qsl(parsed.query, keep_blank_values=True))
    current.update(params)
    return urlunparse(parsed._replace(query=urlencode(current)))
