"""Live-stack MCP Gateway e2e. Talks to compose services, not TestClient."""

from __future__ import annotations

import sys
from uuid import uuid4

import httpx

from onyx.db.enums import MCPTransport
from onyx.server.features.mcp.client import call_mcp_tool, discover_mcp_tools_async

API = "http://api_server:8080"
GATEWAY = "http://mcp_gateway:8091"
MOCK_UPSTREAM = "http://mcp_mock:8000/mcp"
EMAIL = "admin_user@example.com"
PASSWORD = "TestPassword123!"
TOKEN = "dev-mcp-gateway-token"


def login(client: httpx.Client) -> None:
    response = client.post(
        f"{API}/auth/login",
        data={"username": EMAIL, "password": PASSWORD},
    )
    response.raise_for_status()
    if "fastapiusersauth" not in client.cookies:
        raise RuntimeError("login did not set auth cookie")


def main() -> int:
    slug = f"e2e-{uuid4().hex[:8]}"
    gateway_headers = {
        "Authorization": f"Bearer {TOKEN}",
        "X-Onyx-Tenant-Id": "public",
    }
    with httpx.Client(timeout=60.0, follow_redirects=True) as client:
        health = client.get(f"{GATEWAY}/health")
        health.raise_for_status()
        assert health.json()["service"] == "mcp_gateway"
        print("gateway health ok")

        login(client)
        packs = client.get(f"{API}/admin/mcp-gateway/packs")
        packs.raise_for_status()
        slugs = {item["slug"] for item in packs.json()}
        assert {"generic_http", "patsnap", "qixinbao", "tianyancha"} <= slugs
        print(f"packs ok: {sorted(slugs)}")

        created = client.post(
            f"{API}/admin/mcp-gateway/providers",
            json={
                "slug": slug,
                "pack_slug": "generic_http",
                "upstream_url": MOCK_UPSTREAM,
                "credentials": {"api_key": "unused"},
                "enabled": True,
                "attach_mcp_server": True,
            },
        )
        created.raise_for_status()
        body = created.json()
        provider_id = body["id"]
        gateway_url = body["gateway_url"]
        assert gateway_url.endswith(f"/p/{slug}")
        print(f"provider created id={provider_id} url={gateway_url}")

        try:
            policies = client.get(f"{API}/admin/mcp-gateway/providers/{slug}/policies")
            policies.raise_for_status()
            assert any(item["tool_name"] == "*" for item in policies.json())

            import asyncio

            tools = asyncio.run(
                discover_mcp_tools_async(
                    f"{GATEWAY}/p/{slug}",
                    connection_headers=gateway_headers,
                    transport=MCPTransport.STREAMABLE_HTTP,
                )
            )
            names = {tool.name for tool in tools}
            assert "hello" in names
            print(f"tools/list via gateway: {len(names)} tools")

            first = call_mcp_tool(
                f"{GATEWAY}/p/{slug}",
                "hello",
                {"name": "Ada"},
                connection_headers=gateway_headers,
                transport=MCPTransport.STREAMABLE_HTTP,
            )
            second = call_mcp_tool(
                f"{GATEWAY}/p/{slug}",
                "hello",
                {"name": "Ada"},
                connection_headers=gateway_headers,
                transport=MCPTransport.STREAMABLE_HTTP,
            )
            assert "Hello, Ada" in first
            assert first == second
            print(f"tool calls ok: {first!r}")

            stats = client.get(
                f"{API}/admin/mcp-gateway/stats",
                params={"provider_slug": slug},
            )
            stats.raise_for_status()
            payload = stats.json()
            print(f"stats: {payload}")
            assert payload["total_calls"] >= 2
            assert payload["upstream_billed"] == 1
            assert payload["saved_calls"] >= 1
            print("cache dedupe ok")
        finally:
            deleted = client.delete(f"{API}/admin/mcp-gateway/providers/{provider_id}")
            deleted.raise_for_status()
            print("provider deleted")
    return 0


if __name__ == "__main__":
    sys.exit(main())
