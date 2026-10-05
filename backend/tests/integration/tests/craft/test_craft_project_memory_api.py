"""Craft project memory switch API surface (P5): owner-only flip and
round-trip through the project detail response."""

from __future__ import annotations

from uuid import uuid4

from tests.integration.common_utils.constants import API_SERVER_URL
from tests.integration.common_utils.http_client import client
from tests.integration.common_utils.managers.user import UserManager
from tests.integration.common_utils.test_models import DATestUser


def _url(*parts: str) -> str:
    return f"{API_SERVER_URL}/craft-projects" + ("/" + "/".join(parts) if parts else "")


def _create_project(user: DATestUser, name: str) -> dict:
    response = client.post(
        _url(),
        json={"name": name, "description": "", "instructions": None},
        headers=user.headers,
        cookies=user.cookies,
    )
    response.raise_for_status()
    return response.json()


def test_memory_flag_roundtrip_and_default_off(admin_user: DATestUser) -> None:
    project = _create_project(admin_user, f"P5 mem {uuid4().hex[:6]}")
    assert project["memory_enabled"] is False

    patched = client.patch(
        _url(project["id"]),
        json={"memory_enabled": True},
        headers=admin_user.headers,
        cookies=admin_user.cookies,
    )
    patched.raise_for_status()
    assert patched.json()["memory_enabled"] is True

    detail = client.get(
        _url(project["id"]),
        headers=admin_user.headers,
        cookies=admin_user.cookies,
    )
    detail.raise_for_status()
    assert detail.json()["memory_enabled"] is True

    off = client.patch(
        _url(project["id"]),
        json={"memory_enabled": False},
        headers=admin_user.headers,
        cookies=admin_user.cookies,
    )
    off.raise_for_status()
    assert off.json()["memory_enabled"] is False


def test_non_owner_cannot_flip_memory_flag(
    admin_user: DATestUser,  # noqa: ARG001 — seeds a valid admin session env
) -> None:
    owner = UserManager.create(name=f"p5-owner-{uuid4().hex[:6]}")
    project = _create_project(owner, f"P5 guarded {uuid4().hex[:6]}")
    stranger = UserManager.create(name=f"p5-stranger-{uuid4().hex[:6]}")

    # A stranger cannot even see the project (NOT_FOUND masking).
    denied = client.patch(
        _url(project["id"]),
        json={"memory_enabled": True},
        headers=stranger.headers,
        cookies=stranger.cookies,
    )
    assert denied.status_code == 404
