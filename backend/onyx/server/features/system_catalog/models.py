"""Request and response models for the system catalog (gallery + admin)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Self
from uuid import UUID

from pydantic import BaseModel, Field

from onyx.db.enums import (
    ReportTemplateKind,
    SystemCatalogCategory,
    SystemCatalogOrigin,
    SystemCatalogPublishStatus,
)
from onyx.db.models import (
    ReportTemplate,
    Scenario,
    Skill,
    SystemReportTemplate,
    SystemScenario,
    SystemSkill,
)
from onyx.server.features.report_template.models import PlaceholderSpecResponse
from onyx.server.features.scenario.playbook import ScenarioPlaybook
from onyx.db.system_catalog.constants import (
    BODY_MAX,
    CHANGELOG_MAX,
    DESCRIPTION_MAX,
    NAME_MAX,
    SKILL_NAME_MAX,
    SLUG_MAX,
)

CatalogEntry = SystemSkill | SystemScenario | SystemReportTemplate


class CatalogItemSummary(BaseModel):
    """Fields every catalog entry exposes, in both the gallery and the admin UI."""

    id: UUID
    slug: str
    name: str
    description: str
    category: SystemCatalogCategory
    tags: list[str]
    publish_status: SystemCatalogPublishStatus
    version: int
    changelog: str
    origin: SystemCatalogOrigin
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_entry(cls, entry: CatalogEntry) -> Self:
        return cls(
            id=entry.id,
            slug=entry.slug,
            name=entry.name,
            description=entry.description,
            category=entry.category,
            tags=list(entry.tags),
            publish_status=entry.publish_status,
            version=entry.version,
            changelog=entry.changelog,
            origin=entry.origin,
            published_at=entry.published_at,
            created_at=entry.created_at,
            updated_at=entry.updated_at,
        )


class SystemSkillResponse(CatalogItemSummary):
    is_built_in_content: bool
    # Only populated on the detail endpoint; listing many skills would mean
    # reading one bundle per row.
    instructions_markdown: str | None = None

    @classmethod
    def from_skill(
        cls, entry: SystemSkill, *, instructions_markdown: str | None = None
    ) -> "SystemSkillResponse":
        base = CatalogItemSummary.from_entry(entry)
        return cls(
            **base.model_dump(),
            is_built_in_content=entry.built_in_skill_id is not None,
            instructions_markdown=instructions_markdown,
        )


class CatalogBoundSkill(BaseModel):
    slug: str
    name: str
    description: str
    publish_status: SystemCatalogPublishStatus


class CatalogBoundTemplate(BaseModel):
    slug: str
    name: str


class SystemScenarioResponse(CatalogItemSummary):
    rules: dict[str, Any]
    skill_slugs: list[str]
    report_template_slug: str | None
    # Detail endpoint only; listing skips the extra skill/template lookups.
    bound_skills: list[CatalogBoundSkill] | None = None
    report_template: CatalogBoundTemplate | None = None

    @classmethod
    def from_scenario(
        cls,
        entry: SystemScenario,
        *,
        bound_skills: list[CatalogBoundSkill] | None = None,
        report_template: CatalogBoundTemplate | None = None,
    ) -> "SystemScenarioResponse":
        base = CatalogItemSummary.from_entry(entry)
        return cls(
            **base.model_dump(),
            rules=dict(entry.rules or {}),
            skill_slugs=list(entry.skill_slugs),
            report_template_slug=entry.report_template_slug,
            bound_skills=bound_skills,
            report_template=report_template,
        )


class SystemReportTemplateResponse(CatalogItemSummary):
    body: str
    kind: ReportTemplateKind
    placeholders: list[PlaceholderSpecResponse]
    asset_filename: str | None

    @classmethod
    def from_report_template(
        cls, entry: SystemReportTemplate
    ) -> "SystemReportTemplateResponse":
        base = CatalogItemSummary.from_entry(entry)
        return cls(
            **base.model_dump(),
            body=entry.body,
            kind=entry.kind,
            placeholders=[
                PlaceholderSpecResponse.from_stored(item)
                for item in entry.placeholders
            ],
            asset_filename=entry.asset_filename,
        )


class SystemSkillListResponse(BaseModel):
    items: list[SystemSkillResponse]


class SystemScenarioListResponse(BaseModel):
    items: list[SystemScenarioResponse]


class SystemReportTemplateListResponse(BaseModel):
    items: list[SystemReportTemplateResponse]


class ForkResponse(BaseModel):
    """What the caller needs to navigate to the new personal copy."""

    id: UUID
    name: str

    @classmethod
    def from_skill(cls, skill: Skill) -> "ForkResponse":
        return cls(id=skill.id, name=skill.name)

    @classmethod
    def from_scenario(cls, scenario: Scenario) -> "ForkResponse":
        return cls(id=scenario.id, name=scenario.name)

    @classmethod
    def from_report_template(cls, template: ReportTemplate) -> "ForkResponse":
        return cls(id=template.id, name=template.name)


class SystemSkillCreateRequest(BaseModel):
    slug: str = Field(min_length=1, max_length=SLUG_MAX)
    name: str = Field(min_length=1, max_length=SKILL_NAME_MAX)
    description: str = Field(min_length=1, max_length=DESCRIPTION_MAX)
    category: SystemCatalogCategory = SystemCatalogCategory.GENERAL
    tags: list[str] = Field(default_factory=list)
    # Reference an on-disk built-in instead of uploading a bundle. The bundle
    # path uses the separate multipart endpoint.
    built_in_skill_id: str | None = None


class SystemSkillPatchRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=SKILL_NAME_MAX)
    description: str | None = Field(
        default=None, min_length=1, max_length=DESCRIPTION_MAX
    )
    category: SystemCatalogCategory | None = None
    tags: list[str] | None = None


class SystemScenarioCreateRequest(BaseModel):
    slug: str = Field(min_length=1, max_length=SLUG_MAX)
    name: str = Field(min_length=1, max_length=NAME_MAX)
    description: str = Field(min_length=1, max_length=DESCRIPTION_MAX)
    category: SystemCatalogCategory = SystemCatalogCategory.GENERAL
    tags: list[str] = Field(default_factory=list)
    rules: ScenarioPlaybook = Field(default_factory=ScenarioPlaybook)
    skill_slugs: list[str] = Field(default_factory=list)
    report_template_slug: str | None = None


class SystemScenarioPatchRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=NAME_MAX)
    description: str | None = Field(
        default=None, min_length=1, max_length=DESCRIPTION_MAX
    )
    category: SystemCatalogCategory | None = None
    tags: list[str] | None = None
    rules: ScenarioPlaybook | None = None
    skill_slugs: list[str] | None = None
    report_template_slug: str | None = None
    # Explicit, because report_template_slug=None already means "unchanged".
    clear_report_template: bool = False


class SystemReportTemplateCreateRequest(BaseModel):
    slug: str = Field(min_length=1, max_length=SLUG_MAX)
    name: str = Field(min_length=1, max_length=NAME_MAX)
    description: str = Field(min_length=1, max_length=DESCRIPTION_MAX)
    body: str = Field(min_length=1, max_length=BODY_MAX)
    category: SystemCatalogCategory = SystemCatalogCategory.GENERAL
    tags: list[str] = Field(default_factory=list)


class SystemReportTemplatePatchRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=NAME_MAX)
    description: str | None = Field(
        default=None, min_length=1, max_length=DESCRIPTION_MAX
    )
    body: str | None = Field(default=None, min_length=1, max_length=BODY_MAX)
    category: SystemCatalogCategory | None = None
    tags: list[str] | None = None


class PublishRequest(BaseModel):
    changelog: str = Field(default="", max_length=CHANGELOG_MAX)
