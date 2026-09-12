"""Read-only gallery endpoints plus fork, for regular users.

Only PUBLISHED entries are reachable here. Drafts and archived entries report as
missing so a user cannot probe for unreleased content.
"""

from __future__ import annotations

import io
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, Query
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
from onyx.db.system_catalog.constants import require_published
from onyx.db.system_catalog.fork import (
    fork_system_report_template_for_user,
    fork_system_scenario_for_user,
    fork_system_skill_for_user,
)
from onyx.db.system_catalog.report_template import (
    get_system_report_template,
    list_system_report_templates,
    read_catalog_docx_asset,
)
from onyx.report_templates.docx_template import DOCX_CONTENT_TYPE
from onyx.db.system_catalog.scenario import get_system_scenario, list_system_scenarios
from onyx.db.system_catalog.skill import get_system_skill, list_system_skills
from onyx.server.features.build.api import require_onyx_craft_enabled
from onyx.server.features.system_catalog.models import (
    ForkResponse,
    SystemReportTemplateListResponse,
    SystemReportTemplateResponse,
    SystemScenarioListResponse,
    SystemScenarioResponse,
    SystemSkillListResponse,
    SystemSkillResponse,
)
from onyx.server.features.system_catalog.instructions import (
    read_catalog_skill_instructions,
)

router = APIRouter(
    prefix="/craft/gallery",
    dependencies=[Depends(require_onyx_craft_enabled)],
)

_PUBLISHED_ONLY = [SystemCatalogPublishStatus.PUBLISHED]


@router.get("/skills")
def list_gallery_skills(
    q: str | None = None,
    category: SystemCatalogCategory | None = None,
    tags: list[str] | None = Query(default=None),
    _: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    db_session: Session = Depends(get_session),
) -> SystemSkillListResponse:
    entries = list_system_skills(
        db_session,
        query=q,
        category=category,
        tags=tags,
        statuses=_PUBLISHED_ONLY,
    )
    return SystemSkillListResponse(
        items=[SystemSkillResponse.from_skill(entry) for entry in entries]
    )


@router.get("/skills/{entry_id}")
def get_gallery_skill(
    entry_id: UUID,
    _: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    db_session: Session = Depends(get_session),
) -> SystemSkillResponse:
    entry = require_published(get_system_skill(db_session, entry_id))
    return SystemSkillResponse.from_skill(
        entry,
        instructions_markdown=read_catalog_skill_instructions(db_session, entry),
    )


@router.post("/skills/{entry_id}/fork")
def fork_gallery_skill(
    entry_id: UUID,
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    db_session: Session = Depends(get_session),
) -> ForkResponse:
    entry = get_system_skill(db_session, entry_id)
    skill = fork_system_skill_for_user(db_session, entry, user)
    db_session.commit()
    return ForkResponse.from_skill(skill)


@router.get("/scenarios")
def list_gallery_scenarios(
    q: str | None = None,
    category: SystemCatalogCategory | None = None,
    tags: list[str] | None = Query(default=None),
    _: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    db_session: Session = Depends(get_session),
) -> SystemScenarioListResponse:
    entries = list_system_scenarios(
        db_session,
        query=q,
        category=category,
        tags=tags,
        statuses=_PUBLISHED_ONLY,
    )
    return SystemScenarioListResponse(
        items=[SystemScenarioResponse.from_scenario(entry) for entry in entries]
    )


@router.get("/scenarios/{entry_id}")
def get_gallery_scenario(
    entry_id: UUID,
    _: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    db_session: Session = Depends(get_session),
) -> SystemScenarioResponse:
    entry = require_published(get_system_scenario(db_session, entry_id))
    return SystemScenarioResponse.from_scenario(entry)


@router.post("/scenarios/{entry_id}/fork")
def fork_gallery_scenario(
    entry_id: UUID,
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    db_session: Session = Depends(get_session),
) -> ForkResponse:
    entry = get_system_scenario(db_session, entry_id)
    scenario = fork_system_scenario_for_user(db_session, entry, user)
    db_session.commit()
    return ForkResponse.from_scenario(scenario)


@router.get("/report-templates")
def list_gallery_report_templates(
    q: str | None = None,
    category: SystemCatalogCategory | None = None,
    tags: list[str] | None = Query(default=None),
    _: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    db_session: Session = Depends(get_session),
) -> SystemReportTemplateListResponse:
    entries = list_system_report_templates(
        db_session,
        query=q,
        category=category,
        tags=tags,
        statuses=_PUBLISHED_ONLY,
    )
    return SystemReportTemplateListResponse(
        items=[
            SystemReportTemplateResponse.from_report_template(entry)
            for entry in entries
        ]
    )


@router.get("/report-templates/{entry_id}")
def get_gallery_report_template(
    entry_id: UUID,
    _: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    db_session: Session = Depends(get_session),
) -> SystemReportTemplateResponse:
    entry = require_published(get_system_report_template(db_session, entry_id))
    return SystemReportTemplateResponse.from_report_template(entry)


@router.get("/report-templates/{entry_id}/docx")
def download_gallery_report_template_docx(
    entry_id: UUID,
    _: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    db_session: Session = Depends(get_session),
) -> StreamingResponse:
    entry = require_published(get_system_report_template(db_session, entry_id))
    payload = read_catalog_docx_asset(entry)
    filename = entry.asset_filename or f"{entry.slug}.docx"
    return StreamingResponse(
        io.BytesIO(payload),
        media_type=DOCX_CONTENT_TYPE,
        headers={
            "Content-Disposition": f'attachment; filename="{quote(filename)}"'
        },
    )


@router.post("/report-templates/{entry_id}/fork")
def fork_gallery_report_template(
    entry_id: UUID,
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    db_session: Session = Depends(get_session),
) -> ForkResponse:
    entry = get_system_report_template(db_session, entry_id)
    template = fork_system_report_template_for_user(db_session, entry, user)
    db_session.commit()
    return ForkResponse.from_report_template(template)
