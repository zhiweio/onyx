"""Report template HTTP API: CRUD and referenced delete block."""

from __future__ import annotations

from uuid import uuid4

from tests.integration.common_utils.constants import API_SERVER_URL
from tests.integration.common_utils.http_client import client
from tests.integration.common_utils.managers.user import UserManager
from tests.integration.common_utils.test_models import DATestUser


def _url(*parts: str) -> str:
    return f"{API_SERVER_URL}/report-templates" + (
        "/" + "/".join(parts) if parts else ""
    )


def _create_template(user: DATestUser, **body: object) -> dict:
    slug = f"itest_{uuid4().hex[:8]}"
    payload = {
        "name": f"Itest {slug}",
        "slug": slug,
        "description": "Integration template",
        "body": "# Heading\n\n1. Section",
        **body,
    }
    response = client.post(
        _url(),
        json=payload,
        headers=user.headers,
        cookies=user.cookies,
    )
    response.raise_for_status()
    return response.json()


def test_list_includes_seeded_templates(admin_user: DATestUser) -> None:
    response = client.get(
        _url(), headers=admin_user.headers, cookies=admin_user.cookies
    )
    response.raise_for_status()
    slugs = {row["slug"] for row in response.json()["templates"]}
    assert {
        "compliance_risk",
        "policy_trend",
        "target_landscape",
        "patent_fto",
        "clinical_pipeline",
        "cmc_quality",
    } <= slugs


def test_create_get_patch_and_delete_unused(admin_user: DATestUser) -> None:
    created = _create_template(admin_user, name="Unused outline")
    assert created["can_edit"] is True
    assert created["can_delete"] is True
    assert created["referenced_count"] == 0

    detail = client.get(
        _url(created["id"]),
        headers=admin_user.headers,
        cookies=admin_user.cookies,
    )
    detail.raise_for_status()
    assert detail.json()["body"].startswith("# Heading")

    patched = client.patch(
        _url(created["id"]),
        json={"name": "Updated outline", "body": "# Updated\n\n1. A"},
        headers=admin_user.headers,
        cookies=admin_user.cookies,
    )
    patched.raise_for_status()
    assert patched.json()["name"] == "Updated outline"
    assert patched.json()["slug"] == created["slug"]

    deleted = client.delete(
        _url(created["id"]),
        headers=admin_user.headers,
        cookies=admin_user.cookies,
    )
    assert deleted.status_code == 200


def test_cannot_delete_referenced_template(admin_user: DATestUser) -> None:
    created = _create_template(admin_user, name="Referenced outline")
    pack = client.post(
        f"{API_SERVER_URL}/scenarios",
        json={
            "name": f"Pack {uuid4().hex[:6]}",
            "description": "Uses the template",
            "skill_ids": [],
            "report_template": created["slug"],
        },
        headers=admin_user.headers,
        cookies=admin_user.cookies,
    )
    pack.raise_for_status()

    blocked = client.delete(
        _url(created["id"]),
        headers=admin_user.headers,
        cookies=admin_user.cookies,
    )
    assert blocked.status_code == 409
    body = blocked.json()
    assert body["error_code"] == "CONFLICT"
    assert body["referenced_count"] == 1

    client.delete(
        f"{API_SERVER_URL}/scenarios/{pack.json()['id']}",
        headers=admin_user.headers,
        cookies=admin_user.cookies,
    )
    freed = client.delete(
        _url(created["id"]),
        headers=admin_user.headers,
        cookies=admin_user.cookies,
    )
    assert freed.status_code == 200


def test_basic_user_cannot_edit_workspace_template(
    admin_user: DATestUser,
) -> None:
    listed = client.get(
        _url(), headers=admin_user.headers, cookies=admin_user.cookies
    )
    listed.raise_for_status()
    workspace = next(
        row
        for row in listed.json()["templates"]
        if row["slug"] == "compliance_risk"
    )
    basic = UserManager.create(name="report-template-basic")
    denied = client.patch(
        _url(workspace["id"]),
        json={"description": "should fail"},
        headers=basic.headers,
        cookies=basic.cookies,
    )
    assert denied.status_code == 403
