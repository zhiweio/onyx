from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from onyx.db.enums import MCPGatewayAuthAdapter
from onyx.db.models import MCPGatewayProvider
from onyx.utils.sensitive import SensitiveValue


def provider_credentials(provider: MCPGatewayProvider) -> dict[str, Any]:
    raw = provider.credentials
    if isinstance(raw, SensitiveValue):
        value = raw.get_value(apply_mask=False)
        return value if isinstance(value, dict) else {}
    return raw if isinstance(raw, dict) else {}


def apply_auth(
    provider: MCPGatewayProvider,
) -> tuple[str, dict[str, str]]:
    """Return (upstream_url, headers) for the commercial MCP."""
    creds = provider_credentials(provider)
    url = provider.upstream_url
    headers: dict[str, str] = {}
    extra = creds.get("extra_headers")
    if isinstance(extra, dict):
        headers.update({str(key): str(value) for key, value in extra.items()})

    adapter = provider.auth_adapter
    token = str(creds.get("api_key") or creds.get("authorization") or "")
    if adapter == MCPGatewayAuthAdapter.BEARER and token:
        headers["Authorization"] = f"Bearer {token}"
    elif adapter == MCPGatewayAuthAdapter.RAW_AUTHORIZATION and token:
        headers["Authorization"] = token
    elif adapter == MCPGatewayAuthAdapter.QUERY_APIKEY and token:
        url = _append_query(url, {"apikey": token})
    elif adapter == MCPGatewayAuthAdapter.HEADER_MAP:
        pass
    return url, headers


def _append_query(url: str, params: dict[str, str]) -> str:
    parsed = urlparse(url)
    current = dict(parse_qsl(parsed.query, keep_blank_values=True))
    current.update(params)
    return urlunparse(parsed._replace(query=urlencode(current)))
