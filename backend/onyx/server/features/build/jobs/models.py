from uuid import UUID

from pydantic import BaseModel, Field

from onyx.db.enums import CraftJobSpecialistStatus, CraftJobStatus
from onyx.db.models import CraftJob, CraftJobSpecialist


class CraftJobCreateRequest(BaseModel):
    session_id: UUID
    project_id: UUID | None = None
    scenario_id: UUID | None = None
    name: str | None = None
    domain: str | None = None
    prompt: str | None = None
    start: bool = True
    total_budget_seconds: int | None = None
    phase_budget_seconds: int | None = None


class CraftJobPhaseResponse(BaseModel):
    id: str
    name: str
    kind: str
    status: str


class CraftJobSpecialistResponse(BaseModel):
    id: UUID
    session_id: UUID
    role: str
    status: CraftJobSpecialistStatus
    error_detail: str | None = None

    @classmethod
    def from_model(cls, row: CraftJobSpecialist) -> "CraftJobSpecialistResponse":
        return cls(
            id=row.id,
            session_id=row.session_id,
            role=row.role,
            status=row.status,
            error_detail=row.error_detail,
        )


class CraftJobResponse(BaseModel):
    id: UUID
    session_id: UUID
    project_id: UUID | None
    scenario_id: UUID | None
    name: str
    domain: str
    status: CraftJobStatus
    current_phase_index: int
    phases: list[CraftJobPhaseResponse]
    total_budget_seconds: int
    phase_budget_seconds: int
    error_detail: str | None
    specialists: list[CraftJobSpecialistResponse] = Field(default_factory=list)

    @classmethod
    def from_model(cls, job: CraftJob) -> "CraftJobResponse":
        phases = [
            CraftJobPhaseResponse(
                id=str(phase.get("id") or ""),
                name=str(phase.get("name") or phase.get("id") or ""),
                kind=str(phase.get("kind") or ""),
                status=str(phase.get("status") or "pending"),
            )
            for phase in job.phases or []
        ]
        return cls(
            id=job.id,
            session_id=job.session_id,
            project_id=job.project_id,
            scenario_id=job.scenario_id,
            name=job.name,
            domain=job.domain,
            status=job.status,
            current_phase_index=job.current_phase_index,
            phases=phases,
            total_budget_seconds=job.total_budget_seconds,
            phase_budget_seconds=job.phase_budget_seconds,
            error_detail=job.error_detail,
            specialists=[
                CraftJobSpecialistResponse.from_model(row) for row in job.specialists
            ],
        )


class CraftJobStartResponse(BaseModel):
    job: CraftJobResponse
    turn_id: UUID | None = None


class SpecialistCreateItem(BaseModel):
    role: str
    prompt: str


class SpecialistsCreateRequest(BaseModel):
    specialists: list[SpecialistCreateItem]
    project_id: UUID | None = None
