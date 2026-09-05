"""Database operations for Craft report templates."""

from __future__ import annotations

import re
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from onyx.auth.permissions import has_global_permission
from onyx.db.enums import Permission
from onyx.db.models import ReportTemplate, Scenario, User
from onyx.error_handling.error_codes import OnyxErrorCode
from onyx.error_handling.exceptions import OnyxError

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
    return db_session.scalar(
        select(ReportTemplate).where(ReportTemplate.slug == slug)
    )


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
        raise OnyxError(
            OnyxErrorCode.DUPLICATE_RESOURCE, "Template ID already exists"
        )
    db_session.refresh(template)
    return template


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
    db_session.delete(template)
    db_session.commit()
