"""Normalize admin pack credentials before they are stored on a catalog entry."""

from __future__ import annotations

from typing import Any

from onyx.db.enums import MCPGatewayAuthAdapter
from onyx.mcp_gateway.models import ProviderPack


def strip_bearer_prefix(token: str) -> str:
    value = token.strip()
    if value.lower().startswith("bearer "):
        return value[7:].strip()
    return value


def normalize_pack_credentials(
    pack: ProviderPack, credentials: dict[str, Any] | None
) -> dict[str, Any]:
    """Shape admin `{api_key}` input for the pack's auth adapter.

    HEADER_MAP stores the token only in ``extra_headers``. Bearer adapters
    store a bare ``api_key`` (the gateway adds ``Authorization``).
    """
    raw = dict(credentials or {})
    token = strip_bearer_prefix(
        str(raw.get("api_key") or raw.get("authorization") or "")
    )
    if pack.auth_adapter == MCPGatewayAuthAdapter.HEADER_MAP:
        extra = dict(raw.get("extra_headers") or {})
        header_name = pack.auth_header_name or "X-api-key"
        if token:
            extra[header_name] = token
        return {"extra_headers": extra} if extra else {}
    if token:
        raw["api_key"] = token
        raw.pop("authorization", None)
    return raw
