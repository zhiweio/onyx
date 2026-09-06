"""Craft Project HTTP API: CRUD, files, and ownership."""

from __future__ import annotations

import io
from uuid import uuid4

from tests.integration.common_utils.constants import API_SERVER_URL
from tests.integration.common_utils.http_client import client
from tests.integration.common_utils.managers.user import UserManager
from tests.integration.common_utils.test_models import DATestUser


def _url(*parts: str) -> str:
    return f"{API_SERVER_URL}/craft-projects" + (
        "/" + "/".join(parts) if parts else ""
    )


def _create_project(user: DATestUser, name: str, **body: object) -> dict:
    response = client.post(
        _url(),
        json={"name": name, "description": "", "instructions": None, **body},
        headers=user.headers,
        cookies=user.cookies,
    )
    response.raise_for_status()
    return response.json()


def test_create_list_and_get_project(admin_user: DATestUser) -> None:
    name = f"Tax pack {uuid4().hex[:6]}"
    created = _create_project(
        admin_user,
        name,
        description="Shared work files",
        instructions="Cite the source.",
    )
    assert created["name"] == name
    assert created["file_count"] == 0
    assert created["sessions"] == []

    listed = client.get(
        _url(), headers=admin_user.headers, cookies=admin_user.cookies
    )
    listed.raise_for_status()
    names = {row["name"] for row in listed.json()["projects"]}
    assert name in names

    detail = client.get(
        _url(created["id"]),
        headers=admin_user.headers,
        cookies=admin_user.cookies,
    )
    detail.raise_for_status()
    assert detail.json()["instructions"] == "Cite the source."


def test_upload_download_and_delete_file(admin_user: DATestUser) -> None:
    project = _create_project(admin_user, f"Files {uuid4().hex[:6]}")
    payload = b"xlsx-bytes-" + uuid4().hex.encode()
    upload = client.post(
        _url(project["id"], "files"),
        files={"file": ("rates.xlsx", io.BytesIO(payload), "application/octet-stream")},
        headers={
            key: value
            for key, value in admin_user.headers.items()
            if key.lower() != "content-type"
        },
        cookies=admin_user.cookies,
    )
    upload.raise_for_status()
    file_row = upload.json()
    assert file_row["name"] == "rates.xlsx"
    assert file_row["source"] == "upload"

    download = client.get(
        _url(project["id"], "files", file_row["id"]),
        headers=admin_user.headers,
        cookies=admin_user.cookies,
    )
    download.raise_for_status()
    assert download.content == payload

    deleted = client.delete(
        _url(project["id"], "files", file_row["id"]),
        headers=admin_user.headers,
        cookies=admin_user.cookies,
    )
    assert deleted.status_code == 204


def test_other_user_gets_404(admin_user: DATestUser) -> None:
    project = _create_project(admin_user, f"Private {uuid4().hex[:6]}")
    other = UserManager.create(name=f"craft-proj-{uuid4().hex[:8]}")

    response = client.get(
        _url(project["id"]),
        headers=other.headers,
        cookies=other.cookies,
    )
    assert response.status_code == 404

    upload = client.post(
        _url(project["id"], "files"),
        files={"file": ("secret.bin", io.BytesIO(b"nope"), "application/octet-stream")},
        headers={
            key: value
            for key, value in other.headers.items()
            if key.lower() != "content-type"
        },
        cookies=other.cookies,
    )
    assert upload.status_code == 404


def test_delete_project_unbinds_and_hides_row(admin_user: DATestUser) -> None:
    project = _create_project(admin_user, f"Drop {uuid4().hex[:6]}")
    deleted = client.delete(
        _url(project["id"]),
        headers=admin_user.headers,
        cookies=admin_user.cookies,
    )
    assert deleted.status_code == 204

    missing = client.get(
        _url(project["id"]),
        headers=admin_user.headers,
        cookies=admin_user.cookies,
    )
    assert missing.status_code == 404
