"""Signed tokens for API server to gateway calls.

The gateway serves every tenant from one process, so it has to know which
tenant a request belongs to. Reading that from a request header, as the first
version did, means anyone holding the shared secret can name any tenant and
read its cache. Instead the API server mints a short-lived token naming both
the tenant and the catalog entry, and the gateway takes the tenant from the
verified claims — never from a header.

Tokens are minted per call rather than stored, so a leaked one expires on its
own. `MCP_GATEWAY_INTERNAL_TOKEN` is the signing secret; without it the gateway
refuses every request rather than falling open.
"""

import time
from dataclasses import dataclass

import jwt

from onyx.configs.app_configs import (
    MCP_GATEWAY_INTERNAL_TOKEN,
    MCP_GATEWAY_TOKEN_TTL_SECONDS,
)

_ALGORITHM = "HS256"
_ISSUER = "onyx-api"
_AUDIENCE = "onyx-mcp-gateway"


class GatewayTokenError(Exception):
    """The token is missing, malformed, expired, or signed with another key."""


@dataclass(frozen=True)
class GatewayClaims:
    tenant_id: str
    catalog_slug: str
    user_email: str | None


def gateway_signing_secret() -> str:
    return MCP_GATEWAY_INTERNAL_TOKEN


def mint_gateway_token(
    *, tenant_id: str, catalog_slug: str, user_email: str | None = None
) -> str:
    secret = gateway_signing_secret()
    if not secret:
        raise GatewayTokenError(
            "MCP_GATEWAY_INTERNAL_TOKEN is not set; cannot reach the gateway"
        )
    now = int(time.time())
    payload = {
        "iss": _ISSUER,
        "aud": _AUDIENCE,
        "iat": now,
        "exp": now + MCP_GATEWAY_TOKEN_TTL_SECONDS,
        "tenant_id": tenant_id,
        "slug": catalog_slug,
    }
    if user_email:
        payload["email"] = user_email
    return jwt.encode(payload, secret, algorithm=_ALGORITHM)


def verify_gateway_token(token: str) -> GatewayClaims:
    secret = gateway_signing_secret()
    if not secret:
        raise GatewayTokenError("MCP gateway signing secret is not configured")
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=[_ALGORITHM],
            audience=_AUDIENCE,
            issuer=_ISSUER,
        )
    except jwt.PyJWTError as error:
        raise GatewayTokenError(str(error)) from error

    tenant_id = payload.get("tenant_id")
    catalog_slug = payload.get("slug")
    if not isinstance(tenant_id, str) or not isinstance(catalog_slug, str):
        raise GatewayTokenError("Token is missing tenant or catalog claims")

    email = payload.get("email")
    return GatewayClaims(
        tenant_id=tenant_id,
        catalog_slug=catalog_slug,
        user_email=email if isinstance(email, str) else None,
    )
