"""Full-detail and bundle-download endpoints on the user ``/skills`` surface.

Covers ``GET /skills/{id}/detail`` (any visible skill, built-in or custom,
with instructions, file listing, and share details) and
``GET /skills/{id}/bundle`` (zip download), plus the zip-overwrite flow on
``PUT /skills/custom/{id}/bundle``.
"""

from __future__ import annotations

import io
import zipfile
from uuid import uuid4

from onyx.server.features.skill.models import SkillEditableDetailResponse
from tests.integration.common_utils.constants import API_SERVER_URL
from tests.integration.common_utils.http_client import client
from tests.integration.common_utils.managers.skill import (
    SkillManager,
    build_minimal_bundle,
)
from tests.integration.common_utils.test_models import DATestUser


def _build_bundle_with_file(name: str, description: str, extra: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "SKILL.md",
            f"---\nname: {name}\ndescription: {description}\n---\n\nBody of {name}.",
        )
        zf.writestr("references/notes.md", extra)
    return buf.getvalue()


def test_detail_returns_full_content_for_viewer(
    basic_user: DATestUser,
    admin_user: DATestUser,  # noqa: ARG001
) -> None:
    name = f"detail-viewer-{uuid4().hex[:6]}"
    description = f"Description for {name}"
    skill = SkillManager.create_custom(
        admin_user,
        name=name,
        description=description,
        is_public=True,
        bundle_bytes=_build_bundle_with_file(name, description, "shared notes"),
    )

    response = client.get(
        f"{API_SERVER_URL}/skills/{skill.id}/detail",
        headers=basic_user.headers,
    )
    assert response.status_code == 200
    detail = SkillEditableDetailResponse.model_validate(response.json())
    assert detail.name == name
    assert detail.description == description
    assert detail.instructions_markdown == f"Body of {name}."
    assert [bundle_file.path for bundle_file in detail.files] == ["references/notes.md"]
    # Viewers see sharing metadata too: the detail view hides nothing.
    assert detail.public_permission == "VIEWER"
    assert detail.user_permission == "VIEWER"
    assert detail.author_email == admin_user.email
    assert detail.created_at is not None
    assert detail.updated_at is not None


def test_detail_builtin_skill(
    basic_user: DATestUser,
    admin_user: DATestUser,  # noqa: ARG001
) -> None:
    skills = SkillManager.list_for_user(basic_user)
    builtin = skills.builtins[0]

    response = client.get(
        f"{API_SERVER_URL}/skills/{builtin.id}/detail",
        headers=basic_user.headers,
    )
    assert response.status_code == 200
    detail = SkillEditableDetailResponse.model_validate(response.json())
    assert detail.source == "builtin"
    assert detail.instructions_markdown
    assert detail.files
    assert any(bundle_file.path.startswith("SKILL.md") for bundle_file in detail.files)


def test_detail_and_download_hidden_for_private_skill(
    basic_user: DATestUser,
    admin_user: DATestUser,
) -> None:
    skill = SkillManager.create_custom(
        admin_user,
        name=f"detail-private-{uuid4().hex[:6]}",
    )

    detail_response = client.get(
        f"{API_SERVER_URL}/skills/{skill.id}/detail",
        headers=basic_user.headers,
    )
    assert detail_response.status_code == 404

    download_response = client.get(
        f"{API_SERVER_URL}/skills/{skill.id}/bundle",
        headers=basic_user.headers,
    )
    assert download_response.status_code == 404


def test_download_custom_bundle_round_trip(
    basic_user: DATestUser,
    admin_user: DATestUser,  # noqa: ARG001
) -> None:
    name = f"download-zip-{uuid4().hex[:6]}"
    description = f"Description for {name}"
    bundle_bytes = _build_bundle_with_file(name, description, "note body")
    skill = SkillManager.create_custom(
        admin_user,
        name=name,
        description=description,
        is_public=True,
        bundle_bytes=bundle_bytes,
    )

    response = client.get(
        f"{API_SERVER_URL}/skills/{skill.id}/bundle",
        headers=basic_user.headers,
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert f"{name}.zip" in response.headers.get("content-disposition", "")

    with zipfile.ZipFile(io.BytesIO(response.content)) as downloaded:
        assert sorted(downloaded.namelist()) == [
            "SKILL.md",
            "references/notes.md",
        ]
        skill_md = downloaded.read("SKILL.md").decode("utf-8")
        assert f"name: {name}" in skill_md
        assert downloaded.read("references/notes.md") == b"note body"


def test_download_builtin_bundle(
    basic_user: DATestUser,
    admin_user: DATestUser,  # noqa: ARG001
) -> None:
    skills = SkillManager.list_for_user(basic_user)
    builtin = skills.builtins[0]

    response = client.get(
        f"{API_SERVER_URL}/skills/{builtin.id}/bundle",
        headers=basic_user.headers,
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(response.content)) as downloaded:
        names = downloaded.namelist()
        assert any(name.startswith("SKILL.md") for name in names)


def test_replace_bundle_overwrites_and_detail_follows(
    admin_user: DATestUser,
    basic_user: DATestUser,  # noqa: ARG001
) -> None:
    name = f"overwrite-zip-{uuid4().hex[:6]}"
    skill = SkillManager.create_custom(
        admin_user,
        name=name,
        is_public=True,
    )

    new_description = f"Overwritten description for {name}"
    replacement = _build_bundle_with_file(name, new_description, "v2 notes")
    replaced = SkillManager.replace_bundle(skill, replacement, admin_user)
    assert replaced.description == new_description

    detail_response = client.get(
        f"{API_SERVER_URL}/skills/{skill.id}/detail",
        headers=admin_user.headers,
    )
    assert detail_response.status_code == 200
    detail = SkillEditableDetailResponse.model_validate(detail_response.json())
    assert detail.description == new_description
    assert [bundle_file.path for bundle_file in detail.files] == ["references/notes.md"]

    download_response = client.get(
        f"{API_SERVER_URL}/skills/{skill.id}/bundle",
        headers=admin_user.headers,
    )
    assert download_response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(download_response.content)) as downloaded:
        assert downloaded.read("references/notes.md") == b"v2 notes"


def test_replace_bundle_rejects_name_change(
    admin_user: DATestUser,
) -> None:
    skill = SkillManager.create_custom(
        admin_user,
        name=f"rename-guard-{uuid4().hex[:6]}",
        is_public=True,
    )

    response = client.put(
        f"{API_SERVER_URL}/skills/custom/{skill.id}/bundle",
        files={
            "bundle": (
                "other.zip",
                io.BytesIO(build_minimal_bundle("a-different-name")),
                "application/zip",
            )
        },
        headers={
            key: value
            for key, value in admin_user.headers.items()
            if key.lower() != "content-type"
        },
    )
    assert response.status_code == 400
    assert response.json()["error_code"] == "INVALID_INPUT"


def test_replace_bundle_denied_for_viewer(
    admin_user: DATestUser,
    basic_user: DATestUser,  # noqa: ARG001
) -> None:
    skill = SkillManager.create_custom(
        admin_user,
        name=f"viewer-write-{uuid4().hex[:6]}",
        is_public=True,
    )

    response = client.put(
        f"{API_SERVER_URL}/skills/custom/{skill.id}/bundle",
        files={
            "bundle": (
                f"{skill.name}.zip",
                io.BytesIO(build_minimal_bundle(skill.name)),
                "application/zip",
            )
        },
        headers={
            key: value
            for key, value in basic_user.headers.items()
            if key.lower() != "content-type"
        },
    )
    assert response.status_code == 404
