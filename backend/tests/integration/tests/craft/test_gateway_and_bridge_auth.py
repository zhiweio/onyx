"""Auth matrix for the LLM gateway and the agent-tools bridge, hit directly
against the live api_server.

These are the two PAT-facing surfaces craft sandboxes depend on; the matrix
pins the exact contract fixed in fix-round 1/2:

- no credentials        -> 401 (never a silent 404/403)
- wrong-scope PAT       -> 403 INSUFFICIENT_PERMISSIONS
- use:llm_gateway PAT   -> 200 on /gateway/v1/models and the bridge endpoints

LLM-free by design: /models and the MCP initialize handshake prove routing +
auth without spending tokens.
"""

from typing import Any

from onyx.db.enums import Permission
from tests.integration.common_utils.constants import API_SERVER_URL
from tests.integration.common_utils.http_client import client
from tests.integration.common_utils.managers.pat import PATManager
from tests.integration.common_utils.test_models import DATestUser

GATEWAY_MODELS = f"{API_SERVER_URL}/gateway/v1/models"
BRIDGE_MCP = f"{API_SERVER_URL}/build/agent-tools/mcp"
BRIDGE_DEFINITIONS = f"{API_SERVER_URL}/build/agent-tools/definitions"

MCP_INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-03-26",
        "capabilities": {},
        "clientInfo": {"name": "auth-matrix", "version": "0"},
    },
}


def _pat(user: DATestUser, name: str, scopes: list[Permission]) -> str:
    pat = PATManager.create(
        name=name,
        expiration_days=None,
        user_performing_action=user,
        scopes=scopes,
    )
    assert pat.token, "PAT creation did not return a raw token"
    return pat.token


def _assert_unauthenticated(resp: Any) -> None:
    # The OnyxError handler maps a missing credential to 403 + UNAUTHORIZED
    # (not a bare 401); pin the semantic, tolerate either status.
    assert resp.status_code in (401, 403), resp.text
    assert resp.json()["error_code"] == "UNAUTHORIZED", resp.text


def test_gateway_rejects_missing_credentials() -> None:
    resp = client.post(
        f"{API_SERVER_URL}/gateway/v1/chat/completions",
        json={"model": "1/any", "messages": []},
    )
    _assert_unauthenticated(resp)


def test_bridge_rejects_missing_credentials() -> None:
    resp = client.post(BRIDGE_MCP, json=MCP_INITIALIZE)
    _assert_unauthenticated(resp)


def test_wrong_scope_pat_is_forbidden_on_both_surfaces(
    admin_user: DATestUser,
) -> None:
    token = _pat(admin_user, "matrix-read-only", [Permission.READ_SEARCH])
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.post(
        f"{API_SERVER_URL}/gateway/v1/chat/completions",
        headers=headers,
        json={"model": "1/any", "messages": []},
    )
    assert resp.status_code == 403, resp.text
    assert resp.json()["error_code"] == "INSUFFICIENT_PERMISSIONS"

    resp = client.post(BRIDGE_MCP, headers=headers, json=MCP_INITIALIZE)
    assert resp.status_code == 403, resp.text
    assert resp.json()["error_code"] == "INSUFFICIENT_PERMISSIONS"


def test_gateway_scope_lists_models(admin_user: DATestUser) -> None:
    token = _pat(admin_user, "matrix-gateway", [Permission.USE_LLM_GATEWAY])
    resp = client.get(GATEWAY_MODELS, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert isinstance(body.get("data"), list) and body["data"], (
        "gateway model catalog should list the seeded provider's models"
    )


def test_bridge_scope_initializes_platform_tools(admin_user: DATestUser) -> None:
    token = _pat(admin_user, "matrix-bridge", [Permission.USE_LLM_GATEWAY])
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.post(BRIDGE_MCP, headers=headers, json=MCP_INITIALIZE)
    assert resp.status_code == 200, resp.text
    result = resp.json()["result"]
    assert result["serverInfo"]["name"] == "onyx-platform-tools"

    resp = client.get(BRIDGE_DEFINITIONS, headers=headers)
    assert resp.status_code == 200, resp.text
    tool_names = {tool["name"] for tool in resp.json()["tools"]}
    assert "rag_search" in tool_names, tool_names
