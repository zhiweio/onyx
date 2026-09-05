"""Admin endpoints that own the system catalog.

Admins create and edit catalog entries freely; nothing reaches users until
``/publish`` projects the entry into the runtime tables. ``/unpublish`` removes
that projection and archives the entry, leaving user forks alone.
"""

from __future__ import annotations

import io
from typing import Annotated
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from onyx.auth.permissions import require_permission
from onyx.db.engine.sql_engine import get_session
from onyx.db.enums import (
    Permission,
    SystemCatalogCategory,
    SystemCatalogPublishStatus,
)
from onyx.db.models import User
from onyx.db.system_catalog.publish import (
    publish_system_report_template,
    publish_system_scenario,
    publish_system_skill,
    unpublish_system_report_template,
    unpublish_system_scenario,
    unpublish_system_skill,
)
from onyx.db.system_catalog.report_template import (
    attach_catalog_docx_asset,
    create_system_report_template,
    delete_system_report_template,
    get_system_report_template,
    list_system_report_templates,
    read_catalog_docx_asset,
    update_system_report_template,
)
from onyx.report_templates.docx_template import DOCX_CONTENT_TYPE
from onyx.db.system_catalog.scenario import (
    create_system_scenario,
    delete_system_scenario,
    get_system_scenario,
    list_system_scenarios,
    update_system_scenario,
)
from onyx.db.system_catalog.skill import (
    create_system_skill,
    delete_system_skill,
    get_system_skill,
    list_system_skills,
    update_system_skill,
)
from onyx.error_handling.error_codes import OnyxErrorCode
from onyx.error_handling.exceptions import OnyxError
from onyx.file_store.file_store import get_default_file_store
from onyx.server.features.system_catalog.models import (
    PublishRequest,
    SystemReportTemplateCreateRequest,
    SystemReportTemplateListResponse,
    SystemReportTemplatePatchRequest,
    SystemReportTemplateResponse,
    SystemScenarioCreateRequest,
    SystemScenarioListResponse,
    SystemScenarioPatchRequest,
    SystemScenarioResponse,
    SystemSkillCreateRequest,
    SystemSkillListResponse,
    SystemSkillPatchRequest,
    SystemSkillResponse,
)
from onyx.skills.built_in import BUILT_IN_SKILLS
from onyx.skills.bundle import read_bundle_file
from onyx.skills.ingest import ingested_skill_bundle

# Deliberately not behind require_onyx_craft_enabled: an admin curating the
# catalog need not have Craft enabled for their own account, matching the
# existing Craft admin router.
admin_router = APIRouter(
    prefix="/admin/craft/catalog",
    dependencies=[Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS))],
)


# ── skills ────────────────────────────────────────────────────────────────


@admin_router.get("/skills")
def list_catalog_skills(
    q: str | None = None,
    category: SystemCatalogCategory | None = None,
    status: list[SystemCatalogPublishStatus] | None = Query(default=None),
    _: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> SystemSkillListResponse:
    entries = list_system_skills(
        db_session, query=q, category=category, statuses=status
    )
    return SystemSkillListResponse(
        items=[SystemSkillResponse.from_skill(entry) for entry in entries]
    )


@admin_router.post("/skills")
def create_catalog_skill(
    request: SystemSkillCreateRequest,
    _: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> SystemSkillResponse:
    """Register an on-disk built-in skill in the catalog.

    Uploaded bundles use ``POST /skills/upload`` instead, which needs multipart.
    """
    if request.built_in_skill_id is None:
        raise OnyxError(
            OnyxErrorCode.INVALID_INPUT,
            "Provide built_in_skill_id, or upload a bundle instead",
        )
    if request.built_in_skill_id not in BUILT_IN_SKILLS:
        raise OnyxError(
            OnyxErrorCode.INVALID_INPUT,
            f"Unknown built-in skill '{request.built_in_skill_id}'",
        )
    entry = create_system_skill(
        db_session,
        slug=request.slug,
        name=request.name,
        description=request.description,
        category=request.category,
        tags=request.tags,
        built_in_skill_id=request.built_in_skill_id,
    )
    db_session.commit()
    return SystemSkillResponse.from_skill(entry)


@admin_router.post("/skills/upload")
def create_catalog_skill_from_bundle(
    bundle: UploadFile = File(...),
    slug: Annotated[str, Form()] = "",
    category: Annotated[SystemCatalogCategory, Form()] = SystemCatalogCategory.GENERAL,
    tags: Annotated[str, Form()] = "",
    _: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> SystemSkillResponse:
    """Create a catalog skill from an uploaded bundle.

    Name and description come from the bundle's SKILL.md frontmatter, which is
    the single source of truth for skill identity everywhere else too.
    """
    file_store = get_default_file_store()
    with ingested_skill_bundle(
        read_bundle_file(bundle.file), bundle.filename, file_store
    ) as ingested:
        entry = create_system_skill(
            db_session,
            slug=slug or ingested.canonical_name,
            name=ingested.canonical_name,
            description=ingested.description,
            category=category,
            tags=_split_form_tags(tags),
            bundle_file_id=ingested.bundle_file_id,
            bundle_sha256=ingested.bundle_sha256,
        )
        db_session.commit()
    return SystemSkillResponse.from_skill(entry)


def _split_form_tags(raw: str) -> list[str]:
    return [part for part in (chunk.strip() for chunk in raw.split(",")) if part]


@admin_router.get("/skills/{entry_id}")
def get_catalog_skill(
    entry_id: UUID,
    _: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> SystemSkillResponse:
    return SystemSkillResponse.from_skill(get_system_skill(db_session, entry_id))


@admin_router.patch("/skills/{entry_id}")
def patch_catalog_skill(
    entry_id: UUID,
    request: SystemSkillPatchRequest,
    _: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> SystemSkillResponse:
    entry = update_system_skill(
        db_session,
        get_system_skill(db_session, entry_id),
        name=request.name,
        description=request.description,
        category=request.category,
        tags=request.tags,
    )
    db_session.commit()
    return SystemSkillResponse.from_skill(entry)


@admin_router.post("/skills/{entry_id}/publish")
def publish_catalog_skill(
    entry_id: UUID,
    request: PublishRequest,
    user: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> SystemSkillResponse:
    entry = get_system_skill(db_session, entry_id)
    publish_system_skill(db_session, entry, publisher=user, changelog=request.changelog)
    db_session.commit()
    return SystemSkillResponse.from_skill(entry)


@admin_router.post("/skills/{entry_id}/unpublish")
def unpublish_catalog_skill(
    entry_id: UUID,
    _: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> SystemSkillResponse:
    entry = get_system_skill(db_session, entry_id)
    unpublish_system_skill(db_session, entry)
    db_session.commit()
    return SystemSkillResponse.from_skill(entry)


@admin_router.delete("/skills/{entry_id}")
def delete_catalog_skill(
    entry_id: UUID,
    _: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> None:
    entry = get_system_skill(db_session, entry_id)
    _assert_not_published(entry.publish_status)
    delete_system_skill(db_session, entry)
    db_session.commit()


def _assert_not_published(status: SystemCatalogPublishStatus) -> None:
    if status is SystemCatalogPublishStatus.PUBLISHED:
        raise OnyxError(
            OnyxErrorCode.CONFLICT,
            "Unpublish this entry before deleting it",
        )


# ── scenarios ─────────────────────────────────────────────────────────────


@admin_router.get("/scenarios")
def list_catalog_scenarios(
    q: str | None = None,
    category: SystemCatalogCategory | None = None,
    status: list[SystemCatalogPublishStatus] | None = Query(default=None),
    _: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> SystemScenarioListResponse:
    entries = list_system_scenarios(
        db_session, query=q, category=category, statuses=status
    )
    return SystemScenarioListResponse(
        items=[SystemScenarioResponse.from_scenario(entry) for entry in entries]
    )


@admin_router.post("/scenarios")
def create_catalog_scenario(
    request: SystemScenarioCreateRequest,
    _: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> SystemScenarioResponse:
    entry = create_system_scenario(
        db_session,
        slug=request.slug,
        name=request.name,
        description=request.description,
        category=request.category,
        tags=request.tags,
        rules=request.rules,
        skill_slugs=request.skill_slugs,
        report_template_slug=request.report_template_slug,
    )
    db_session.commit()
    return SystemScenarioResponse.from_scenario(entry)


@admin_router.get("/scenarios/{entry_id}")
def get_catalog_scenario(
    entry_id: UUID,
    _: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> SystemScenarioResponse:
    return SystemScenarioResponse.from_scenario(
        get_system_scenario(db_session, entry_id)
    )


@admin_router.patch("/scenarios/{entry_id}")
def patch_catalog_scenario(
    entry_id: UUID,
    request: SystemScenarioPatchRequest,
    _: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> SystemScenarioResponse:
    entry = update_system_scenario(
        db_session,
        get_system_scenario(db_session, entry_id),
        name=request.name,
        description=request.description,
        category=request.category,
        tags=request.tags,
        rules=request.rules,
        skill_slugs=request.skill_slugs,
        report_template_slug=request.report_template_slug,
        clear_report_template=request.clear_report_template,
    )
    db_session.commit()
    return SystemScenarioResponse.from_scenario(entry)


@admin_router.post("/scenarios/{entry_id}/publish")
def publish_catalog_scenario(
    entry_id: UUID,
    request: PublishRequest,
    user: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> SystemScenarioResponse:
    entry = get_system_scenario(db_session, entry_id)
    publish_system_scenario(
        db_session, entry, publisher=user, changelog=request.changelog
    )
    db_session.commit()
    return SystemScenarioResponse.from_scenario(entry)


@admin_router.post("/scenarios/{entry_id}/unpublish")
def unpublish_catalog_scenario(
    entry_id: UUID,
    _: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> SystemScenarioResponse:
    entry = get_system_scenario(db_session, entry_id)
    unpublish_system_scenario(db_session, entry)
    db_session.commit()
    return SystemScenarioResponse.from_scenario(entry)


@admin_router.delete("/scenarios/{entry_id}")
def delete_catalog_scenario(
    entry_id: UUID,
    _: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> None:
    entry = get_system_scenario(db_session, entry_id)
    _assert_not_published(entry.publish_status)
    delete_system_scenario(db_session, entry)
    db_session.commit()


# ── report templates ──────────────────────────────────────────────────────


@admin_router.get("/report-templates")
def list_catalog_report_templates(
    q: str | None = None,
    category: SystemCatalogCategory | None = None,
    status: list[SystemCatalogPublishStatus] | None = Query(default=None),
    _: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> SystemReportTemplateListResponse:
    entries = list_system_report_templates(
        db_session, query=q, category=category, statuses=status
    )
    return SystemReportTemplateListResponse(
        items=[
            SystemReportTemplateResponse.from_report_template(entry)
            for entry in entries
        ]
    )


@admin_router.post("/report-templates")
def create_catalog_report_template(
    request: SystemReportTemplateCreateRequest,
    _: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> SystemReportTemplateResponse:
    entry = create_system_report_template(
        db_session,
        slug=request.slug,
        name=request.name,
        description=request.description,
        body=request.body,
        category=request.category,
        tags=request.tags,
    )
    db_session.commit()
    return SystemReportTemplateResponse.from_report_template(entry)


@admin_router.get("/report-templates/{entry_id}")
def get_catalog_report_template(
    entry_id: UUID,
    _: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> SystemReportTemplateResponse:
    return SystemReportTemplateResponse.from_report_template(
        get_system_report_template(db_session, entry_id)
    )


@admin_router.patch("/report-templates/{entry_id}")
def patch_catalog_report_template(
    entry_id: UUID,
    request: SystemReportTemplatePatchRequest,
    _: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> SystemReportTemplateResponse:
    entry = update_system_report_template(
        db_session,
        get_system_report_template(db_session, entry_id),
        name=request.name,
        description=request.description,
        body=request.body,
        category=request.category,
        tags=request.tags,
    )
    db_session.commit()
    return SystemReportTemplateResponse.from_report_template(entry)


@admin_router.post("/report-templates/{entry_id}/docx")
def upload_catalog_report_template_docx(
    entry_id: UUID,
    asset: UploadFile = File(...),
    _: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> SystemReportTemplateResponse:
    """Attach or replace the Word document behind a catalog template.

    The change stays in the catalog until the entry is published again, so a
    live projection keeps serving the previously published document.
    """
    entry = get_system_report_template(db_session, entry_id)
    content = asset.file.read()
    if not content:
        raise OnyxError(OnyxErrorCode.INVALID_INPUT, "The uploaded file is empty")
    entry = attach_catalog_docx_asset(
        db_session, entry, asset_bytes=content, filename=asset.filename
    )
    db_session.commit()
    return SystemReportTemplateResponse.from_report_template(entry)


@admin_router.get("/report-templates/{entry_id}/docx")
def download_catalog_report_template_docx(
    entry_id: UUID,
    _: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> StreamingResponse:
    entry = get_system_report_template(db_session, entry_id)
    payload = read_catalog_docx_asset(entry)
    filename = entry.asset_filename or f"{entry.slug}.docx"
    return StreamingResponse(
        io.BytesIO(payload),
        media_type=DOCX_CONTENT_TYPE,
        headers={
            "Content-Disposition": f'attachment; filename="{quote(filename)}"'
        },
    )


@admin_router.post("/report-templates/{entry_id}/publish")
def publish_catalog_report_template(
    entry_id: UUID,
    request: PublishRequest,
    user: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> SystemReportTemplateResponse:
    entry = get_system_report_template(db_session, entry_id)
    publish_system_report_template(
        db_session, entry, publisher=user, changelog=request.changelog
    )
    db_session.commit()
    return SystemReportTemplateResponse.from_report_template(entry)


@admin_router.post("/report-templates/{entry_id}/unpublish")
def unpublish_catalog_report_template(
    entry_id: UUID,
    _: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> SystemReportTemplateResponse:
    entry = get_system_report_template(db_session, entry_id)
    unpublish_system_report_template(db_session, entry)
    db_session.commit()
    return SystemReportTemplateResponse.from_report_template(entry)


@admin_router.delete("/report-templates/{entry_id}")
def delete_catalog_report_template(
    entry_id: UUID,
    _: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> None:
    entry = get_system_report_template(db_session, entry_id)
    _assert_not_published(entry.publish_status)
    delete_system_report_template(db_session, entry)
    db_session.commit()
