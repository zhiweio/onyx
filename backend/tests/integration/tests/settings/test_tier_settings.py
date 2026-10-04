"""Integration tests for tier reporting and tier-gated settings writes.

The CE-only build has no license resolver, so every workspace must report
the enterprise tier via GET /api/settings, and the settings the FE gates by
plan — Search Mode (Business+) and chat retention (Enterprise) — must be
writable through PATCH /api/admin/settings without a 402.
"""

from typing import Any

from tests.integration.common_utils.constants import API_SERVER_URL
from tests.integration.common_utils.http_client import client
from tests.integration.common_utils.managers.user import UserManager


def _fetch_settings(headers: dict[str, str]) -> dict[str, Any]:
    response = client.get(f"{API_SERVER_URL}/settings", headers=headers, timeout=60)
    assert response.status_code == 200
    return response.json()


def test_settings_report_enterprise_tier(reset: None) -> None:  # noqa: ARG001
    user = UserManager.create(name="tier_admin")
    assert user.is_admin

    settings = _fetch_settings(user.headers)
    assert settings["tier"] == "enterprise"


def test_tier_gated_settings_are_writable(reset: None) -> None:  # noqa: ARG001
    user = UserManager.create(name="tier_admin")
    assert user.is_admin

    # The reset fixture does not clear the settings KV record, so restore the
    # original values afterwards to keep other tests independent of this one.
    original = _fetch_settings(user.headers)
    try:
        response = client.patch(
            f"{API_SERVER_URL}/admin/settings",
            json={"search_ui_enabled": True, "maximum_chat_retention_days": 30},
            headers=user.headers,
            timeout=60,
        )
        assert response.status_code == 200
        updated = response.json()
        assert updated["search_ui_enabled"] is True
        assert updated["maximum_chat_retention_days"] == 30
    finally:
        restore = client.patch(
            f"{API_SERVER_URL}/admin/settings",
            json={
                "search_ui_enabled": original.get("search_ui_enabled"),
                "maximum_chat_retention_days": original.get(
                    "maximum_chat_retention_days"
                ),
            },
            headers=user.headers,
            timeout=60,
        )
        assert restore.status_code == 200
