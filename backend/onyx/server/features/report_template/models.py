from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from onyx.db.models import ReportTemplate


class ReportTemplateCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    slug: str | None = Field(default=None, max_length=64)
    description: str = ""
    body: str = Field(min_length=1, max_length=100_000)


class ReportTemplatePatchRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = None
    body: str | None = Field(default=None, min_length=1, max_length=100_000)


class ReportTemplateResponse(BaseModel):
    id: UUID
    slug: str
    name: str
    description: str
    body: str
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
