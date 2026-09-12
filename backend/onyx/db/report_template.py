"""Database operations for Craft report templates."""

from __future__ import annotations

import hashlib
import io
import re
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from onyx.auth.permissions import has_global_permission
from onyx.configs.constants import FileOrigin
from onyx.db.enums import Permission, ReportTemplateKind
from onyx.db.models import ReportTemplate, Scenario, User
from onyx.error_handling.error_codes import OnyxErrorCode
from onyx.error_handling.exceptions import OnyxError
from onyx.file_store.file_store import get_default_file_store
from onyx.report_templates.docx_template import (
    DOCX_CONTENT_TYPE,
    validate_docx_asset,
)

SLUG_MAX = 64
NAME_MAX = 128
BODY_MAX = 100_000
_SLUG_CLEAN = re.compile(r"[^a-z0-9]+")


def normalize_report_template_slug(raw: str) -> str:
    slug = _SLUG_CLEAN.sub("_", raw.strip().lower()).strip("_")[:SLUG_MAX]
    if not slug or not slug[0].isalpha():
        raise OnyxError(
            OnyxErrorCode.INVALID_INPUT,
            "Template ID must start with a letter and use letters, numbers, or _",
        )
    return slug


def can_edit_report_template(template: ReportTemplate, user: User) -> bool:
    if template.author_user_id == user.id:
        return True
    if template.author_user_id is None and has_global_permission(
        user, Permission.FULL_ADMIN_PANEL_ACCESS
    ):
        return True
    return False


def count_report_template_references(db_session: Session, slug: str) -> int:
    return int(
        db_session.scalar(
            select(func.count())
            .select_from(Scenario)
            .where(Scenario.report_template == slug)
        )
        or 0
    )


def list_report_templates(db_session: Session) -> list[ReportTemplate]:
    return list(
        db_session.scalars(
            select(ReportTemplate).order_by(
                ReportTemplate.is_builtin.desc(),
                ReportTemplate.name.asc(),
            )
        ).all()
    )


def get_report_template(db_session: Session, template_id: UUID) -> ReportTemplate:
    template = db_session.get(ReportTemplate, template_id)
    if template is None:
        raise OnyxError(OnyxErrorCode.NOT_FOUND, "Report template not found")
    return template


def get_report_template_by_slug(
    db_session: Session, slug: str
) -> ReportTemplate | None:
    return db_session.scalar(select(ReportTemplate).where(ReportTemplate.slug == slug))


def create_report_template(
    db_session: Session,
    *,
    user: User,
    name: str,
    slug: str | None,
    description: str,
    body: str,
) -> ReportTemplate:
    trimmed_name = name.strip()
    if not trimmed_name:
        raise OnyxError(OnyxErrorCode.INVALID_INPUT, "Name is required")
    trimmed_body = body.strip()
    if not trimmed_body:
        raise OnyxError(OnyxErrorCode.INVALID_INPUT, "Structure is required")
    if len(trimmed_body) > BODY_MAX:
        raise OnyxError(OnyxErrorCode.INVALID_INPUT, "Structure is too long")
    resolved_slug = normalize_report_template_slug(slug or trimmed_name)
    template = ReportTemplate(
        slug=resolved_slug,
        name=trimmed_name[:NAME_MAX],
        description=description.strip(),
        body=trimmed_body,
        author_user_id=user.id,
        is_builtin=False,
    )
    db_session.add(template)
    try:
        db_session.commit()
    except IntegrityError:
        db_session.rollback()
        raise OnyxError(OnyxErrorCode.DUPLICATE_RESOURCE, "Template ID already exists")
    db_session.refresh(template)
    return template


def attach_docx_asset(
    db_session: Session,
    template: ReportTemplate,
    user: User,
    *,
    asset_bytes: bytes,
    filename: str | None,
) -> ReportTemplate:
    """Turn a template into a Word template, or replace its asset.

    The file is stored as-is. The agent uses it as a layout reference.
    """
    if not can_edit_report_template(template, user):
        raise OnyxError(OnyxErrorCode.INSUFFICIENT_PERMISSIONS)

    validate_docx_asset(asset_bytes)
    file_store = get_default_file_store()
    previous_file_id = template.asset_file_id
    asset_file_id = file_store.save_file(
        content=io.BytesIO(asset_bytes),
        display_name=f"{template.slug}.docx",
        file_origin=FileOrigin.REPORT_TEMPLATE_ASSET,
        file_type=DOCX_CONTENT_TYPE,
    )
    try:
        template.kind = ReportTemplateKind.DOCX
        template.asset_file_id = asset_file_id
        template.asset_sha256 = hashlib.sha256(asset_bytes).hexdigest()
        template.asset_filename = (filename or f"{template.slug}.docx")[:255]
        db_session.commit()
    except Exception:
        db_session.rollback()
        file_store.delete_file(asset_file_id, error_on_missing=False)
        raise
    if previous_file_id is not None and previous_file_id != asset_file_id:
        # The row now points at the new blob, so the old one is unreachable.
        file_store.delete_file(previous_file_id, error_on_missing=False)
    db_session.refresh(template)
    return template


def read_docx_asset(template: ReportTemplate) -> bytes:
    if template.kind is not ReportTemplateKind.DOCX or template.asset_file_id is None:
        raise OnyxError(OnyxErrorCode.NOT_FOUND, "This template has no Word document")
    return get_default_file_store().read_file(template.asset_file_id).read()


def update_report_template(
    db_session: Session,
    template: ReportTemplate,
    user: User,
    *,
    name: str | None = None,
    description: str | None = None,
    body: str | None = None,
) -> ReportTemplate:
    if not can_edit_report_template(template, user):
        raise OnyxError(OnyxErrorCode.INSUFFICIENT_PERMISSIONS)
    if name is not None:
        trimmed_name = name.strip()
        if not trimmed_name:
            raise OnyxError(OnyxErrorCode.INVALID_INPUT, "Name is required")
        template.name = trimmed_name[:NAME_MAX]
    if description is not None:
        template.description = description.strip()
    if body is not None:
        trimmed_body = body.strip()
        if not trimmed_body:
            raise OnyxError(OnyxErrorCode.INVALID_INPUT, "Structure is required")
        if len(trimmed_body) > BODY_MAX:
            raise OnyxError(OnyxErrorCode.INVALID_INPUT, "Structure is too long")
        template.body = trimmed_body
    db_session.commit()
    db_session.refresh(template)
    return template


def delete_report_template(
    db_session: Session, template: ReportTemplate, user: User
) -> None:
    if not can_edit_report_template(template, user):
        raise OnyxError(OnyxErrorCode.INSUFFICIENT_PERMISSIONS)
    referenced = count_report_template_references(db_session, template.slug)
    if referenced > 0:
        raise OnyxError(
            OnyxErrorCode.CONFLICT,
            "Packs still use this template",
            extra={"referenced_count": referenced},
        )
    asset_file_id = template.asset_file_id
    # A catalog projection only borrows the entry's blob — the catalog row owns
    # it and outlives the projection, so deleting it here would orphan the entry.
    owns_asset = template.system_report_template_id is None
    db_session.delete(template)
    db_session.commit()
    if asset_file_id is not None and owns_asset:
        # Only after the row is gone, so a failed delete never orphans the row
        # from its asset.
        get_default_file_store().delete_file(asset_file_id, error_on_missing=False)
