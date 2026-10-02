from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from onyx.db.enums import ReportTemplateKind
from onyx.db.models import ReportTemplate
from onyx.report_templates.postcheck import Finding


class ReportTemplateCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    slug: str | None = Field(default=None, max_length=64)
    description: str = ""
    body: str = Field(min_length=1, max_length=100_000)
    # Contract-style payloads. ``contract`` non-empty switches the template to
    # the contract+renderer scheme; both are validated server-side.
    contract: dict | None = None
    theme: dict | None = None


class ReportTemplatePatchRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = None
    body: str | None = Field(default=None, min_length=1, max_length=100_000)
    contract: dict | None = None
    theme: dict | None = None


class ReportTemplateResponse(BaseModel):
    id: UUID
    slug: str
    name: str
    description: str
    body: str
    kind: ReportTemplateKind
    contract: dict
    theme: dict
    asset_filename: str | None
    author_user_id: UUID | None
    is_builtin: bool
    referenced_count: int
    can_edit: bool
    can_delete: bool
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(
        cls,
        template: ReportTemplate,
        *,
        referenced_count: int,
        can_edit: bool,
    ) -> "ReportTemplateResponse":
        return cls(
            id=template.id,
            slug=template.slug,
            name=template.name,
            description=template.description,
            body=template.body,
            kind=template.kind,
            contract=dict(template.contract or {}),
            theme=dict(template.theme or {}),
            asset_filename=template.asset_filename,
            author_user_id=template.author_user_id,
            is_builtin=template.is_builtin,
            referenced_count=referenced_count,
            can_edit=can_edit,
            can_delete=can_edit and referenced_count == 0,
            created_at=template.created_at,
            updated_at=template.updated_at,
        )


class ReportTemplateListResponse(BaseModel):
    templates: list[ReportTemplateResponse]


class ReportTemplatePreviewRequest(BaseModel):
    """Render a markdown body with a contract + theme and postcheck it."""

    body: str = Field(min_length=1)
    contract: dict | None = None
    theme: dict | None = None


class ReportTemplatePreviewResponse(BaseModel):
    docx_base64: str
    findings: list[Finding]
