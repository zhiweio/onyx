"""Gateway ops: call history requires a time window."""

from datetime import datetime, timedelta, timezone

from tests.integration.common_utils.constants import API_SERVER_URL
from tests.integration.common_utils.http_client import client
from tests.integration.common_utils.test_models import DATestUser

OPS = f"{API_SERVER_URL}/admin/mcp-gateway"


def test_calls_require_a_time_window(admin_user: DATestUser) -> None:
    missing = client.get(
        f"{OPS}/calls", headers=admin_user.headers, cookies=admin_user.cookies
    )
    assert missing.status_code == 400

    now = datetime.now(timezone.utc)
    windowed = client.get(
        f"{OPS}/calls",
        params={
            "from": (now - timedelta(hours=24)).isoformat(),
            "to": now.isoformat(),
        },
        headers=admin_user.headers,
        cookies=admin_user.cookies,
    )
    windowed.raise_for_status()
    body = windowed.json()
    assert "items" in body
    assert "next_cursor" in body
    for row in body["items"]:
        assert "arguments" not in row
        assert "arguments_preview" in row


def test_stats_require_a_time_window(admin_user: DATestUser) -> None:
    missing = client.get(
        f"{OPS}/stats", headers=admin_user.headers, cookies=admin_user.cookies
    )
    assert missing.status_code == 400

    now = datetime.now(timezone.utc)
    windowed = client.get(
        f"{OPS}/stats",
        params={
            "from": (now - timedelta(hours=24)).isoformat(),
            "to": now.isoformat(),
        },
        headers=admin_user.headers,
        cookies=admin_user.cookies,
    )
    windowed.raise_for_status()
    body = windowed.json()
    assert "total_calls" in body
    assert "hit_rate" in body
