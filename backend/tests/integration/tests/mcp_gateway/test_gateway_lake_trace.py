"""Bind a live mock MCP, invoke it through the gateway, and check Iceberg lineage."""

import socket
import subprocess
import sys
import time
from collections.abc import Generator
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from tests.integration.common_utils.constants import API_SERVER_URL
from tests.integration.common_utils.http_client import client
from tests.integration.common_utils.test_models import DATestUser

ADMIN_MCP = f"{API_SERVER_URL}/admin/mcp"
OPS = f"{API_SERVER_URL}/admin/mcp-gateway"
SETTINGS_URL = f"{API_SERVER_URL}/admin/settings"
SECURITY_URL = f"{API_SERVER_URL}/admin/security"
COMPOSE_DIR = Path(__file__).resolve().parents[5] / "deployment" / "docker_compose"
MOCK_SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "mock_services"
    / "mcp_test_server"
    / "run_mcp_server_no_auth.py"
)


def _set_module_enabled(user: DATestUser, enabled: bool) -> None:
    client.patch(
        SETTINGS_URL,
        json={"mcp_gateway_enabled": enabled},
        headers=user.headers,
        cookies=user.cookies,
    ).raise_for_status()


def _window() -> dict[str, str]:
    now = datetime.now(timezone.utc)
    return {
        "from": (now - timedelta(hours=1)).isoformat(),
        "to": (now + timedelta(hours=1)).isoformat(),
    }


@pytest.fixture
def gateway_ready(admin_user: DATestUser) -> Generator[None, None, None]:
    previous_module = client.get(
        f"{API_SERVER_URL}/settings",
        headers=admin_user.headers,
        cookies=admin_user.cookies,
    )
    previous_module.raise_for_status()
    was_enabled = bool(previous_module.json().get("mcp_gateway_enabled"))
    _set_module_enabled(admin_user, True)

    security = client.get(
        SECURITY_URL, headers=admin_user.headers, cookies=admin_user.cookies
    )
    previous_ssrf = None
    if security.status_code == 200:
        previous_ssrf = security.json().get("ssrf_protection_level")
        client.put(
            SECURITY_URL,
            json={"ssrf_protection_level": "disabled"},
            headers=admin_user.headers,
            cookies=admin_user.cookies,
        ).raise_for_status()
    try:
        yield
    finally:
        if previous_ssrf is not None:
            client.put(
                SECURITY_URL,
                json={"ssrf_protection_level": previous_ssrf},
                headers=admin_user.headers,
                cookies=admin_user.cookies,
            )
        _set_module_enabled(admin_user, was_enabled)


@pytest.fixture
def live_pack_server(
    admin_user: DATestUser,
    gateway_ready: None,  # noqa: ARG001
) -> Generator[dict, None, None]:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = int(sock.getsockname()[1])
    process = subprocess.Popen(
        [sys.executable, str(MOCK_SCRIPT), str(port)],
        cwd=MOCK_SCRIPT.parent,
    )
    start = time.monotonic()
    try:
        while time.monotonic() - start < 15:
            if process.poll() is not None:
                raise RuntimeError("mock MCP server exited during startup")
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(0.2)
                try:
                    sock.connect(("127.0.0.1", port))
                    break
                except OSError:
                    time.sleep(0.1)
        else:
            raise TimeoutError("mock MCP server did not accept connections")

        slug = f"lake-{uuid4().hex[:8]}"
        created = client.post(
            f"{ADMIN_MCP}/servers/from-pack",
            json={
                "pack_slug": "generic_http",
                "name": slug,
                "slug": slug,
                "upstream_url": f"http://host.docker.internal:{port}/mcp",
                "credentials": {"api_key": "lake-trace"},
                "is_public": True,
                "groups": [],
                "users": [],
            },
            headers=admin_user.headers,
            cookies=admin_user.cookies,
        )
        created.raise_for_status()
        server = created.json()
        try:
            yield server
        finally:
            client.delete(
                f"{ADMIN_MCP}/server/{server['id']}",
                headers=admin_user.headers,
                cookies=admin_user.cookies,
            )
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()


def _invoke_hello(slug: str, user_email: str) -> str:
    script = (
        "from onyx.mcp_gateway.tokens import mint_gateway_token\n"
        "from onyx.server.features.mcp.client import call_mcp_tool\n"
        "from shared_configs.configs import POSTGRES_DEFAULT_SCHEMA\n"
        f"token = mint_gateway_token(tenant_id=POSTGRES_DEFAULT_SCHEMA, "
        f"catalog_slug={slug!r}, user_email={user_email!r})\n"
        f"print(call_mcp_tool("
        f"'http://mcp_gateway:8091/p/{slug}', 'hello', {{'name': 'Ada'}}, "
        f"connection_headers={{'Authorization': 'Bearer ' + token}}))\n"
    )
    result = subprocess.run(
        ["docker", "compose", "exec", "-T", "api_server", "python", "-c", script],
        cwd=COMPOSE_DIR,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout)
    return result.stdout


def test_gateway_call_writes_iceberg_fields_and_payload(
    admin_user: DATestUser,
    live_pack_server: dict,
) -> None:
    slug = live_pack_server["catalog_slug"]
    first = _invoke_hello(slug, admin_user.email)
    second = _invoke_hello(slug, admin_user.email)
    assert "Hello, Ada" in first
    assert "Hello, Ada" in second

    window = _window()
    calls = client.get(
        f"{OPS}/calls",
        params={**window, "catalog_slug": slug},
        headers=admin_user.headers,
        cookies=admin_user.cookies,
    )
    calls.raise_for_status()
    body = calls.json()
    assert body["total"] >= 2
    outcomes = {row["outcome"] for row in body["items"]}
    assert "miss" in outcomes
    assert "hit" in outcomes
    miss = next(row for row in body["items"] if row["outcome"] == "miss")
    assert miss["cache_key"]
    assert miss["id"]

    detail = client.get(
        f"{OPS}/calls/{miss['id']}",
        headers=admin_user.headers,
        cookies=admin_user.cookies,
    )
    detail.raise_for_status()
    payload = detail.json()
    assert payload["request_id"]
    assert payload["result_blob_id"]
    assert payload["pack_slug"] == "generic_http"
    assert payload["user_email"] == admin_user.email
    assert payload["arguments"] == {"name": "Ada"}
    assert payload["payload"] is not None
    assert "Hello, Ada" in str(payload["payload"])

    cache = client.get(
        f"{OPS}/cache",
        params={"catalog_slug": slug},
        headers=admin_user.headers,
        cookies=admin_user.cookies,
    )
    cache.raise_for_status()
    cache_items = cache.json()["items"]
    assert cache_items
    entry = cache_items[0]
    assert entry["catalog_slug"] == slug
    assert entry["effective_tool_name"] == "hello"
    assert entry["storage"] == "iceberg"
    assert entry["hit_count"] >= 1

    series = client.get(
        f"{OPS}/stats/series",
        params={**window, "catalog_slug": slug},
        headers=admin_user.headers,
        cookies=admin_user.cookies,
    )
    series.raise_for_status()
    series_body = series.json()
    assert series_body["calls_by_outcome"]
    day = series_body["calls_by_outcome"][0]
    assert day["miss"] >= 1
    assert day["hit"] >= 1

    cleared = client.post(
        f"{OPS}/history/clear",
        json={"cache": True, "calls": True},
        headers=admin_user.headers,
        cookies=admin_user.cookies,
    )
    cleared.raise_for_status()
    after = client.get(
        f"{OPS}/calls",
        params=window,
        headers=admin_user.headers,
        cookies=admin_user.cookies,
    )
    after.raise_for_status()
    assert after.json()["total"] == 0
