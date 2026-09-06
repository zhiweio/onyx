"""CRUD and search for ``system_report_template`` catalog entries."""

from __future__ import annotations

import hashlib
import io
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from onyx.configs.constants import FileOrigin
from onyx.db.enums import (
    ReportTemplateKind,
    SystemCatalogCategory,
    SystemCatalogOrigin,
    SystemCatalogPublishStatus,
)
from onyx.db.models import SystemReportTemplate
from onyx.db.system_catalog.constants import (
    BODY_MAX,
    DESCRIPTION_MAX,
    NAME_MAX,
    apply_tag_filter,
    apply_text_search,
    normalize_report_template_catalog_slug,
    normalize_required_text,
    normalize_tags,
)
from onyx.error_handling.error_codes import OnyxErrorCode
from onyx.error_handling.exceptions import OnyxError
from onyx.file_store.file_store import get_default_file_store
from onyx.report_templates.docx_template import (
    DOCX_CONTENT_TYPE,
    extract_docx_placeholder_schema,
)
from onyx.report_templates.placeholders import PlaceholderSpec
from onyx.utils.logger import setup_logger

logger = setup_logger()


def list_system_report_templates(
    db_session: Session,
    *,
    query: str | None = None,
    category: SystemCatalogCategory | None = None,
    tags: list[str] | None = None,
    statuses: list[SystemCatalogPublishStatus] | None = None,
) -> list[SystemReportTemplate]:
    stmt = select(SystemReportTemplate)
    if statuses:
        stmt = stmt.where(SystemReportTemplate.publish_status.in_(statuses))
    if category is not None:
        stmt = stmt.where(SystemReportTemplate.category == category)
    stmt = apply_text_search(stmt, SystemReportTemplate, query)
    stmt = apply_tag_filter(stmt, SystemReportTemplate, tags)
    stmt = stmt.order_by(
        SystemReportTemplate.category.asc(), SystemReportTemplate.name.asc()
    )
    return list(db_session.scalars(stmt).all())


def get_system_report_template(
    db_session: Session, entry_id: UUID
) -> SystemReportTemplate:
    entry = db_session.get(SystemReportTemplate, entry_id)
    if entry is None:
        raise OnyxError(OnyxErrorCode.NOT_FOUND, "Catalog report template not found")
    return entry


def get_system_report_template_by_slug(
    db_session: Session, slug: str
) -> SystemReportTemplate | None:
    return db_session.scalar(
        select(SystemReportTemplate).where(SystemReportTemplate.slug == slug)
    )


def create_system_report_template(
    db_session: Session,
    *,
    slug: str,
    name: str,
    description: str,
    body: str,
    category: SystemCatalogCategory,
    tags: list[str],
    origin: SystemCatalogOrigin = SystemCatalogOrigin.ADMIN,
) -> SystemReportTemplate:
    entry = SystemReportTemplate(
        slug=normalize_report_template_catalog_slug(slug),
        name=normalize_required_text(name, field="Name", max_length=NAME_MAX),
        description=normalize_required_text(
            description, field="Description", max_length=DESCRIPTION_MAX
        ),
        body=normalize_required_text(body, field="Structure", max_length=BODY_MAX),
        category=category,
        tags=normalize_tags(tags),
        publish_status=SystemCatalogPublishStatus.DRAFT,
        version=0,
        changelog="",
        origin=origin,
    )
    db_session.add(entry)
    try:
        db_session.flush()
    except IntegrityError as exc:
        db_session.rollback()
        raise OnyxError(
            OnyxErrorCode.DUPLICATE_RESOURCE, "Catalog slug already exists"
        ) from exc
    return entry


def update_system_report_template(
    db_session: Session,
    entry: SystemReportTemplate,
    *,
    name: str | None = None,
    description: str | None = None,
    body: str | None = None,
    category: SystemCatalogCategory | None = None,
    tags: list[str] | None = None,
) -> SystemReportTemplate:
    if name is not None:
        entry.name = normalize_required_text(name, field="Name", max_length=NAME_MAX)
    if description is not None:
        entry.description = normalize_required_text(
            description, field="Description", max_length=DESCRIPTION_MAX
        )
    if body is not None:
        entry.body = normalize_required_text(
            body, field="Structure", max_length=BODY_MAX
        )
    if category is not None:
        entry.category = category
    if tags is not None:
        entry.tags = normalize_tags(tags)
    db_session.flush()
    return entry


def attach_catalog_docx_asset(
    db_session: Session,
    entry: SystemReportTemplate,
    *,
    asset_bytes: bytes,
    filename: str | None,
    overlay: list[PlaceholderSpec] | None = None,
) -> SystemReportTemplate:
    """Attach or replace the Word asset on a catalog template.

    Names come from the uploaded document. Overlay only supplies metadata.
    """
    placeholders = extract_docx_placeholder_schema(asset_bytes, overlay)
    file_store = get_default_file_store()
    previous_file_id = entry.asset_file_id
    asset_file_id = file_store.save_file(
        content=io.BytesIO(asset_bytes),
        display_name=f"{entry.slug}.docx",
        file_origin=FileOrigin.REPORT_TEMPLATE_ASSET,
        file_type=DOCX_CONTENT_TYPE,
    )
    try:
        entry.kind = ReportTemplateKind.DOCX
        entry.asset_file_id = asset_file_id
        entry.asset_sha256 = hashlib.sha256(asset_bytes).hexdigest()
        entry.asset_filename = (filename or f"{entry.slug}.docx")[:255]
        entry.placeholders = placeholders
        db_session.flush()
    except Exception:
        file_store.delete_file(asset_file_id, error_on_missing=False)
        raise
    if previous_file_id is not None and previous_file_id != asset_file_id:
        # A published projection borrows the entry's blob, so the old id may
        # still be referenced until the next publish; leave it for that publish
        # to supersede rather than deleting it out from under a live session.
        logger.info(
            "Replaced Word asset for catalog template '%s'; previous blob %s "
            "is superseded on next publish",
            entry.slug,
            previous_file_id,
        )
    return entry


def read_catalog_docx_asset(entry: SystemReportTemplate) -> bytes:
    if entry.kind is not ReportTemplateKind.DOCX or entry.asset_file_id is None:
        raise OnyxError(OnyxErrorCode.NOT_FOUND, "This template has no Word document")
    return get_default_file_store().read_file(entry.asset_file_id).read()


def delete_system_report_template(
    db_session: Session, entry: SystemReportTemplate
) -> None:
    db_session.delete(entry)
    db_session.flush()
