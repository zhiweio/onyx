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
    assert "total" in body
    for row in body["items"]:
        assert "arguments" not in row
        assert "arguments_preview" in row


def test_calls_accept_preset_and_custom_windows(admin_user: DATestUser) -> None:
    now = datetime.now(timezone.utc)
    for days in (1, 7, 30, 90, 180):
        windowed = client.get(
            f"{OPS}/calls",
            params={
                "from": (now - timedelta(days=days)).isoformat(),
                "to": now.isoformat(),
                "q": "nonexistent-tool",
                "offset": 0,
                "limit": 20,
            },
            headers=admin_user.headers,
            cookies=admin_user.cookies,
        )
        windowed.raise_for_status()
        body = windowed.json()
        assert body["total"] == 0
        assert body["items"] == []


def test_stats_report_unlimited_retention(admin_user: DATestUser) -> None:
    now = datetime.now(timezone.utc)
    windowed = client.get(
        f"{OPS}/stats",
        params={
            "from": (now - timedelta(days=90)).isoformat(),
            "to": now.isoformat(),
        },
        headers=admin_user.headers,
        cookies=admin_user.cookies,
    )
    windowed.raise_for_status()
    body = windowed.json()
    assert body["retention_days"] in (None, 0)


def test_cache_accepts_offset_and_search(admin_user: DATestUser) -> None:
    listed = client.get(
        f"{OPS}/cache",
        params={"q": "nonexistent-tool", "offset": 0, "limit": 20},
        headers=admin_user.headers,
        cookies=admin_user.cookies,
    )
    listed.raise_for_status()
    body = listed.json()
    assert "items" in body
    assert "total" in body
    assert body["total"] == 0

    paged = client.get(
        f"{OPS}/cache",
        params={"offset": 20, "limit": 20},
        headers=admin_user.headers,
        cookies=admin_user.cookies,
    )
    paged.raise_for_status()
    paged_body = paged.json()
    assert isinstance(paged_body["items"], list)
    assert isinstance(paged_body["total"], int)
    assert len(paged_body["items"]) <= 20


def test_stats_series_require_a_time_window(admin_user: DATestUser) -> None:
    missing = client.get(
        f"{OPS}/stats/series", headers=admin_user.headers, cookies=admin_user.cookies
    )
    assert missing.status_code == 400

    now = datetime.now(timezone.utc)
    windowed = client.get(
        f"{OPS}/stats/series",
        params={
            "from": (now - timedelta(hours=24)).isoformat(),
            "to": now.isoformat(),
        },
        headers=admin_user.headers,
        cookies=admin_user.cookies,
    )
    windowed.raise_for_status()
    body = windowed.json()
    assert "calls_by_outcome" in body
    assert "latency" in body
    assert "top_servers" in body


def test_history_clear_returns_counts(admin_user: DATestUser) -> None:
    client.patch(
        f"{API_SERVER_URL}/admin/settings",
        json={"mcp_gateway_enabled": True},
        headers=admin_user.headers,
        cookies=admin_user.cookies,
    ).raise_for_status()
    cleared = client.post(
        f"{OPS}/history/clear",
        json={"cache": True, "calls": True},
        headers=admin_user.headers,
        cookies=admin_user.cookies,
    )
    cleared.raise_for_status()
    body = cleared.json()
    assert "cache_entries" in body
    assert "result_pointers" in body

    now = datetime.now(timezone.utc)
    calls = client.get(
        f"{OPS}/calls",
        params={
            "from": (now - timedelta(hours=24)).isoformat(),
            "to": now.isoformat(),
        },
        headers=admin_user.headers,
        cookies=admin_user.cookies,
    )
    calls.raise_for_status()
    assert calls.json()["total"] == 0
    assert calls.json()["items"] == []


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
