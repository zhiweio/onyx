from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from onyx.db.enums import ScenarioAccessLevel, ScenarioSharePermission


class ScenarioUpsertRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str = ""
    rules: dict[str, Any] = Field(default_factory=dict)
    skill_ids: list[UUID] = Field(default_factory=list)
    report_template: str | None = None


class ScenarioPatchRequest(BaseModel):
    name: str | None = Field(default=None, max_length=128)
    description: str | None = None
    rules: dict[str, Any] | None = None
    skill_ids: list[UUID] | None = None
    report_template: str | None = None


class ScenarioShareRequest(BaseModel):
    user_ids: list[UUID] = Field(default_factory=list)
    group_ids: list[int] = Field(default_factory=list)
    public_permission: ScenarioSharePermission | None = None


class ScenarioSkillRef(BaseModel):
    skill_id: UUID
    sort_order: int


class ScenarioResponse(BaseModel):
    id: UUID
    name: str
    description: str
    author_user_id: UUID | None
    public_permission: ScenarioSharePermission | None
    rules: dict[str, Any]
    report_template: str | None
    skill_ids: list[UUID]
    skills: list[ScenarioSkillRef]
    access_level: ScenarioAccessLevel
    shared_user_ids: list[UUID]
    shared_group_ids: list[int]


class ScenarioListResponse(BaseModel):
    scenarios: list[ScenarioResponse]


class ScenarioResolveRequest(BaseModel):
    query: str | None = None


class ScenarioResolveResponse(BaseModel):
    scenario_id: UUID
    skill_ids: list[UUID]
