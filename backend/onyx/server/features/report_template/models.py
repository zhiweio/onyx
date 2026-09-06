from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import BaseModel, Field

from onyx.db.enums import ReportTemplateKind
from onyx.db.models import ReportTemplate
from onyx.report_templates.placeholders import (
    PlaceholderKind,
    normalize_placeholder_schema,
)


class PlaceholderSpecResponse(BaseModel):
    name: str
    kind: PlaceholderKind
    required: bool = True
    description: str = ""
    example: str = ""

    @classmethod
    def from_stored(cls, raw: object) -> Self:
        spec = normalize_placeholder_schema([raw])[0]
        return cls(
            name=spec["name"],
            kind=spec["kind"],
            required=spec["required"],
            description=spec["description"],
            example=spec["example"],
        )


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
    kind: ReportTemplateKind
    placeholders: list[PlaceholderSpecResponse]
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
            placeholders=[
                PlaceholderSpecResponse.from_stored(item)
                for item in template.placeholders
            ],
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
