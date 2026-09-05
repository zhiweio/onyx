from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from onyx.auth.permissions import require_permission
from onyx.db.engine.sql_engine import get_session
from onyx.db.enums import Permission
from onyx.db.models import User
from onyx.db.report_template import (
    can_edit_report_template,
    count_report_template_references,
    create_report_template,
    delete_report_template,
    get_report_template,
    list_report_templates,
    update_report_template,
)
from onyx.server.features.build.api import require_onyx_craft_enabled
from onyx.server.features.report_template.models import (
    ReportTemplateCreateRequest,
    ReportTemplateListResponse,
    ReportTemplatePatchRequest,
    ReportTemplateResponse,
)

router = APIRouter(
    prefix="/report-templates",
    dependencies=[Depends(require_onyx_craft_enabled)],
)


def _to_response(
    db_session: Session, template, user: User
) -> ReportTemplateResponse:
    can_edit = can_edit_report_template(template, user)
    return ReportTemplateResponse.from_model(
        template,
        referenced_count=count_report_template_references(
            db_session, template.slug
        ),
        can_edit=can_edit,
    )


@router.get("")
def list_report_templates_endpoint(
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    db_session: Session = Depends(get_session),
) -> ReportTemplateListResponse:
    rows = list_report_templates(db_session)
    return ReportTemplateListResponse(
        templates=[_to_response(db_session, row, user) for row in rows]
    )


@router.post("")
def create_report_template_endpoint(
    request: ReportTemplateCreateRequest,
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    db_session: Session = Depends(get_session),
) -> ReportTemplateResponse:
    template = create_report_template(
        db_session,
        user=user,
        name=request.name,
        slug=request.slug,
        description=request.description,
        body=request.body,
    )
    return _to_response(db_session, template, user)


@router.get("/{template_id}")
def get_report_template_endpoint(
    template_id: UUID,
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    db_session: Session = Depends(get_session),
) -> ReportTemplateResponse:
    template = get_report_template(db_session, template_id)
    return _to_response(db_session, template, user)


@router.patch("/{template_id}")
def patch_report_template_endpoint(
    template_id: UUID,
    request: ReportTemplatePatchRequest,
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    db_session: Session = Depends(get_session),
) -> ReportTemplateResponse:
    template = get_report_template(db_session, template_id)
    template = update_report_template(
        db_session,
        template,
        user,
        name=request.name,
        description=request.description,
        body=request.body,
    )
    return _to_response(db_session, template, user)


@router.delete("/{template_id}")
def delete_report_template_endpoint(
    template_id: UUID,
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    db_session: Session = Depends(get_session),
) -> None:
    template = get_report_template(db_session, template_id)
    delete_report_template(db_session, template, user)
