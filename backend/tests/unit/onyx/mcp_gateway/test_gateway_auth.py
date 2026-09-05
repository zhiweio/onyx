"""The gateway must take the tenant from a signed token, never from a header.

The first version trusted `X-Onyx-Tenant-Id` behind a single shared secret, so
anyone holding that secret could read any tenant's cache. These tests pin the
replacement.
"""

import time

import jwt
import pytest

from onyx.mcp_gateway.tokens import (
    GatewayTokenError,
    mint_gateway_token,
    verify_gateway_token,
)

# 32+ bytes so PyJWT does not warn about a short HMAC key.
_SECRET = "unit-test-gateway-secret-0123456789abcdef"
_OTHER_SECRET = "another-gateway-secret-0123456789abcdef"


@pytest.fixture(autouse=True)
def signing_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("onyx.mcp_gateway.tokens.MCP_GATEWAY_INTERNAL_TOKEN", _SECRET)


def test_round_trip_carries_tenant_and_slug() -> None:
    token = mint_gateway_token(
        tenant_id="tenant_a", catalog_slug="patsnap", user_email="a@example.com"
    )
    claims = verify_gateway_token(token)
    assert claims.tenant_id == "tenant_a"
    assert claims.catalog_slug == "patsnap"
    assert claims.user_email == "a@example.com"


def test_token_signed_with_another_key_is_rejected() -> None:
    forged = jwt.encode(
        {
            "iss": "onyx-api",
            "aud": "onyx-mcp-gateway",
            "iat": int(time.time()),
            "exp": int(time.time()) + 300,
            "tenant_id": "tenant_victim",
            "slug": "patsnap",
        },
        _OTHER_SECRET,
        algorithm="HS256",
    )
    with pytest.raises(GatewayTokenError):
        verify_gateway_token(forged)


def test_expired_token_is_rejected() -> None:
    stale = jwt.encode(
        {
            "iss": "onyx-api",
            "aud": "onyx-mcp-gateway",
            "iat": int(time.time()) - 600,
            "exp": int(time.time()) - 300,
            "tenant_id": "tenant_a",
            "slug": "patsnap",
        },
        _SECRET,
        algorithm="HS256",
    )
    with pytest.raises(GatewayTokenError):
        verify_gateway_token(stale)


def test_token_from_another_issuer_is_rejected() -> None:
    """A token minted for some other service must not open the gateway."""
    wrong_audience = jwt.encode(
        {
            "iss": "onyx-api",
            "aud": "some-other-service",
            "iat": int(time.time()),
            "exp": int(time.time()) + 300,
            "tenant_id": "tenant_a",
            "slug": "patsnap",
        },
        _SECRET,
        algorithm="HS256",
    )
    with pytest.raises(GatewayTokenError):
        verify_gateway_token(wrong_audience)


def test_token_without_claims_is_rejected() -> None:
    incomplete = jwt.encode(
        {
            "iss": "onyx-api",
            "aud": "onyx-mcp-gateway",
            "iat": int(time.time()),
            "exp": int(time.time()) + 300,
        },
        _SECRET,
        algorithm="HS256",
    )
    with pytest.raises(GatewayTokenError):
        verify_gateway_token(incomplete)


def test_minting_without_a_secret_fails_loudly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No secret must mean no access, not open access."""
    monkeypatch.setattr("onyx.mcp_gateway.tokens.MCP_GATEWAY_INTERNAL_TOKEN", "")
    with pytest.raises(GatewayTokenError):
        mint_gateway_token(tenant_id="tenant_a", catalog_slug="patsnap")
    with pytest.raises(GatewayTokenError):
        verify_gateway_token("anything")
