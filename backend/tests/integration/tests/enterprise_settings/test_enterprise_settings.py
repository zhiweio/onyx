"""Integration tests for the white-label (enterprise settings) API.

Covers the surfaces the frontend white-label experience depends on:
anonymous read access (the login page renders branding pre-auth), the
`ee_features_enabled` gate that makes the frontend fetch these settings at
all, admin-only PATCH with partial-merge semantics, logo upload/delete with
static fallback, favicon behavior, and the custom analytics script endpoint.
"""

import struct
import zlib
from typing import Any

from tests.integration.common_utils.constants import API_SERVER_URL
from tests.integration.common_utils.http_client import client
from tests.integration.common_utils.managers.user import DATestUser, UserManager


def _tiny_png() -> bytes:
    """A 1x1 transparent PNG, assembled directly so no long base64 blob
    (which the secret scanner flags) lands in the test source."""

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)
    # One filter byte + a single transparent RGBA pixel.
    idat = zlib.compress(b"\x00\x00\x00\x00\x00")
    signature = b"\x89PNG\r\n\x1a\n"
    return signature + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


TINY_PNG = _tiny_png()


def _fetch(headers: dict[str, str] | None = None) -> dict[str, Any]:
    response = client.get(
        f"{API_SERVER_URL}/enterprise-settings", headers=headers, timeout=60
    )
    assert response.status_code == 200
    return response.json()


def _restore_defaults(admin_user: DATestUser) -> None:
    response = client.patch(
        f"{API_SERVER_URL}/admin/enterprise-settings",
        json={"application_name": None},
        headers=admin_user.headers,
        timeout=60,
    )
    assert response.status_code == 200


def test_settings_gate_ee_features_enabled(reset: None) -> None:  # noqa: ARG001
    user = UserManager.create(name="enterprise_gate_admin")
    assert user.is_admin

    response = client.get(
        f"{API_SERVER_URL}/settings", headers=user.headers, timeout=60
    )
    assert response.status_code == 200
    # The frontend only fetches enterprise settings (and thus renders the
    # custom brand) when this flag is true; the CE-only build always ships it.
    assert response.json()["ee_features_enabled"] is True


def test_enterprise_settings_readable_anonymously(reset: None) -> None:  # noqa: ARG001
    # No headers: the login page renders branding before authentication.
    settings = _fetch()
    assert "application_name" in settings
    # Internal file-store ids must never leak through the public payload.
    assert "logo_filename" not in settings
    assert "custom_analytics_script" not in settings


def test_admin_patch_partial_merge(reset: None) -> None:  # noqa: ARG001
    admin_user = UserManager.create(name="enterprise_patch_admin")
    assert admin_user.is_admin

    original = _fetch(admin_user.headers)
    try:
        response = client.patch(
            f"{API_SERVER_URL}/admin/enterprise-settings",
            json={"application_name": "Acme AI"},
            headers=admin_user.headers,
            timeout=60,
        )
        assert response.status_code == 200
        updated = response.json()
        assert updated["application_name"] == "Acme AI"
        # Fields the patch did not mention keep their stored values.
        assert updated["use_custom_logo"] == original["use_custom_logo"]
        assert updated["custom_nav_items"] == original["custom_nav_items"]

        # GET reflects the write.
        assert _fetch(admin_user.headers)["application_name"] == "Acme AI"
    finally:
        _restore_defaults(admin_user)


def test_patch_rejects_invalid_color(reset: None) -> None:  # noqa: ARG001
    admin_user = UserManager.create(name="enterprise_color_admin")
    assert admin_user.is_admin

    response = client.patch(
        f"{API_SERVER_URL}/admin/enterprise-settings",
        json={"brand_color": "not-a-color"},
        headers=admin_user.headers,
        timeout=60,
    )
    assert response.status_code == 422


def test_patch_requires_admin(reset: None) -> None:  # noqa: ARG001
    admin_user = UserManager.create(name="enterprise_perm_admin")
    assert admin_user.is_admin
    plain_user = UserManager.create(name="enterprise_perm_plain")
    assert not plain_user.is_admin

    response = client.patch(
        f"{API_SERVER_URL}/admin/enterprise-settings",
        json={"application_name": "Should Not Apply"},
        headers=plain_user.headers,
        timeout=60,
    )
    assert response.status_code == 403
    assert _fetch(admin_user.headers)["application_name"] is None


def test_logo_fallback_then_upload_and_delete(reset: None) -> None:  # noqa: ARG001
    admin_user = UserManager.create(name="enterprise_logo_admin")
    assert admin_user.is_admin

    # No custom logo yet: the endpoint serves the static fallback.
    response = client.get(f"{API_SERVER_URL}/enterprise-settings/logo", timeout=60)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/")

    # Upload: the flag flips on and the endpoint serves the uploaded bytes.
    # Drop the JSON content-type header so httpx can set the multipart one.
    upload_headers = {
        k: v for k, v in admin_user.headers.items() if k.lower() != "content-type"
    }
    upload = client.put(
        f"{API_SERVER_URL}/admin/enterprise-settings/logo",
        files={"file": ("logo.png", TINY_PNG, "image/png")},
        headers=upload_headers,
        timeout=60,
    )
    assert upload.status_code == 200
    assert upload.json()["use_custom_logo"] is True

    served = client.get(f"{API_SERVER_URL}/enterprise-settings/logo", timeout=60)
    assert served.status_code == 200
    assert served.content == TINY_PNG

    # Dark logo endpoint falls back to the uploaded light logo.
    dark = client.get(f"{API_SERVER_URL}/enterprise-settings/logo-dark", timeout=60)
    assert dark.status_code == 200
    assert dark.content == TINY_PNG

    # Delete: back to the static fallback and the flag flips off.
    delete = client.delete(
        f"{API_SERVER_URL}/admin/enterprise-settings/logo",
        headers=admin_user.headers,
        timeout=60,
    )
    assert delete.status_code == 200
    assert delete.json()["use_custom_logo"] is False
    after = client.get(f"{API_SERVER_URL}/enterprise-settings/logo", timeout=60)
    assert after.status_code == 200
    assert after.content != TINY_PNG


def test_favicon_404_without_upload(reset: None) -> None:  # noqa: ARG001
    admin_user = UserManager.create(name="enterprise_favicon_admin")
    assert admin_user.is_admin

    response = client.get(f"{API_SERVER_URL}/enterprise-settings/favicon", timeout=60)
    assert response.status_code == 404


def test_custom_analytics_script_roundtrip(reset: None) -> None:  # noqa: ARG001
    admin_user = UserManager.create(name="enterprise_analytics_admin")
    assert admin_user.is_admin

    script = "window.__acmeAnalytics = true;"
    try:
        patch = client.patch(
            f"{API_SERVER_URL}/admin/enterprise-settings",
            json={"custom_analytics_script": script},
            headers=admin_user.headers,
            timeout=60,
        )
        assert patch.status_code == 200

        served = client.get(
            f"{API_SERVER_URL}/enterprise-settings/custom-analytics-script",
            headers=admin_user.headers,
            timeout=60,
        )
        assert served.status_code == 200
        assert served.json() == script

        # The endpoint is public (the SSR settings fetch runs it pre-auth);
        # the general settings payload still never carries the script source.
        anonymous = client.get(
            f"{API_SERVER_URL}/enterprise-settings/custom-analytics-script",
            timeout=60,
        )
        assert anonymous.status_code == 200
        assert anonymous.json() == script
        assert "custom_analytics_script" not in _fetch(admin_user.headers)
    finally:
        client.patch(
            f"{API_SERVER_URL}/admin/enterprise-settings",
            json={"custom_analytics_script": None},
            headers=admin_user.headers,
            timeout=60,
        )
