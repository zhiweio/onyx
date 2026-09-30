"""Pydantic request / response models for the env-vars API."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from onyx.db.enums import EnvVarScope
from onyx.db.env_var import ENV_VAR_MAX_NAME_LENGTH, ENV_VAR_MAX_VALUE_LENGTH
from onyx.db.models import EnvVar


class _Forbid(BaseModel):
    """Base model that rejects unknown fields."""

    model_config = ConfigDict(extra="forbid")


class EnvVarUpsertRequest(_Forbid):
    """Request body for ``POST /env-vars``."""

    name: str = Field(..., min_length=1, max_length=ENV_VAR_MAX_NAME_LENGTH)
    value: str = Field(..., min_length=1, max_length=ENV_VAR_MAX_VALUE_LENGTH)
    is_secret: bool = False
    scope: EnvVarScope
    project_id: UUID | None = None

    @model_validator(mode="after")
    def _scope_project_pairing(self) -> EnvVarUpsertRequest:
        if self.scope == EnvVarScope.PROJECT and self.project_id is None:
            raise ValueError("project_id is required when scope is 'PROJECT'")
        if self.scope == EnvVarScope.USER and self.project_id is not None:
            raise ValueError("project_id must be omitted when scope is 'USER'")
        return self


class EnvVarPatchRequest(_Forbid):
    """Request body for ``PATCH /env-vars/{id}``.

    Scope is immutable. Secret values are write-only: sending ``value``
    replaces the stored plaintext; it is never returned.
    """

    name: str | None = Field(
        default=None, min_length=1, max_length=ENV_VAR_MAX_NAME_LENGTH
    )
    value: str | None = Field(
        default=None, min_length=1, max_length=ENV_VAR_MAX_VALUE_LENGTH
    )

    @model_validator(mode="after")
    def _at_least_one_field(self) -> EnvVarPatchRequest:
        if self.name is None and self.value is None:
            raise ValueError("At least one of 'name' or 'value' is required")
        return self


class EnvVarResponse(BaseModel):
    """One row. ``value`` is present only for non-secrets — secret values
    are write-only (GitHub Actions semantics). ``manageable`` tells the UI
    whether the caller may edit / delete the row."""

    id: str
    name: str
    is_secret: bool
    scope: EnvVarScope
    project_id: str | None
    project_name: str | None
    value: str | None
    manageable: bool
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(
        cls, row: EnvVar, project_name: str | None, *, manageable: bool
    ) -> EnvVarResponse:
        return cls(
            id=str(row.id),
            name=row.name,
            is_secret=row.is_secret,
            scope=row.scope,
            project_id=str(row.project_id) if row.project_id is not None else None,
            project_name=project_name,
            value=None if row.is_secret else row.value.get_value(apply_mask=False),
            manageable=manageable,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


class EnvVarListResponse(BaseModel):
    items: list[EnvVarResponse]
