from typing import Any
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
    provider: str | None = None
    provider_id: int | None = None
    model: str | None = None


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
    node_id: str | None = None

    @classmethod
    def from_model(cls, row: CraftJobSpecialist) -> "CraftJobSpecialistResponse":
        return cls(
            id=row.id,
            session_id=row.session_id,
            role=row.role,
            status=row.status,
            error_detail=row.error_detail,
            node_id=row.node_id,
        )


class CraftJobArtifactResponse(BaseModel):
    path: str
    summary: str
    producer_node: str = ""


class CraftJobEventResponse(BaseModel):
    type: str
    created_at: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class CraftJobInterruptResponse(BaseModel):
    kind: str
    payload: dict[str, Any] = Field(default_factory=dict)


class CraftJobTimelineItem(BaseModel):
    id: str
    kind: str
    status: str
    label: str


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
    timeline: list[CraftJobTimelineItem] = Field(default_factory=list)
    artifacts: list[CraftJobArtifactResponse] = Field(default_factory=list)
    events: list[CraftJobEventResponse] = Field(default_factory=list)
    interrupt: CraftJobInterruptResponse | None = None

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
        try:
            state = job.state if isinstance(job.state, dict) else {}
        except AttributeError:
            state = {}
        artifacts_value = state.get("artifacts")
        artifacts_raw: dict[str, Any] = (
            artifacts_value if isinstance(artifacts_value, dict) else {}
        )
        interrupt_raw = state.get("interrupt")
        interrupt = None
        if isinstance(interrupt_raw, dict) and interrupt_raw.get("kind"):
            interrupt = CraftJobInterruptResponse(
                kind=str(interrupt_raw.get("kind")),
                payload=dict(interrupt_raw.get("payload") or {}),
            )
        try:
            event_rows = job.events or []
        except AttributeError:
            event_rows = []
        events = [
            CraftJobEventResponse(
                type=row.event_type,
                created_at=row.created_at.isoformat() if row.created_at else None,
                payload=row.payload or {},
            )
            for row in event_rows[-50:]
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
            specialists=_specialist_responses(job),
            timeline=_timeline_from_phases(phases, events),
            artifacts=[
                CraftJobArtifactResponse(
                    path=str(path),
                    summary=str((record or {}).get("summary") or ""),
                    producer_node=str((record or {}).get("producer_node") or ""),
                )
                for path, record in artifacts_raw.items()
                if isinstance(record, dict)
            ],
            events=events,
            interrupt=interrupt,
        )


def _timeline_from_phases(
    phases: list[CraftJobPhaseResponse],
    events: list[CraftJobEventResponse] | None = None,
) -> list[CraftJobTimelineItem]:
    groups: list[tuple[str, str, list[CraftJobPhaseResponse]]] = []
    lanes: list[CraftJobPhaseResponse] = []
    for phase in phases:
        if phase.kind in {"lane", "research_lane"} or phase.id.startswith("lane:"):
            lanes.append(phase)
            continue
        if lanes:
            groups.append(("lanes", "lane", lanes))
            lanes = []
        groups.append((phase.id, phase.kind, [phase]))
    if lanes:
        groups.append(("lanes", "lane", lanes))
    journal = _journal_node_status(events or [])
    items: list[CraftJobTimelineItem] = []
    for group_id, kind, members in groups:
        member_ids = {item.id for item in members}
        if kind == "lane":
            member_ids.add("lanes")
        journal_statuses = [
            journal[node_id] for node_id in member_ids if node_id in journal
        ]
        statuses = {item.status for item in members}
        if "running" in journal_statuses or "running" in statuses:
            status = "running"
        elif journal_statuses and all(item == "succeeded" for item in journal_statuses):
            status = "succeeded"
        elif statuses and statuses <= {"succeeded"}:
            status = "succeeded"
        elif "failed" in journal_statuses or "failed" in statuses:
            status = "failed"
        else:
            status = "pending"
        label = members[0].name if len(members) == 1 else "Lanes"
        items.append(
            CraftJobTimelineItem(id=group_id, kind=kind, status=status, label=label)
        )
    return items


def _specialist_responses(job: CraftJob) -> list[CraftJobSpecialistResponse]:
    try:
        rows = job.specialists
    except AttributeError:
        return []
    return [CraftJobSpecialistResponse.from_model(row) for row in rows]


def _journal_node_status(events: list[CraftJobEventResponse]) -> dict[str, str]:
    status: dict[str, str] = {}
    for event in events:
        node_id = str((event.payload or {}).get("node_id") or "")
        if event.type in {"node.start", "lane.start"} and node_id:
            status[node_id] = "running"
        elif event.type == "node.end" and node_id:
            status[node_id] = "succeeded"
        elif event.type == "lane.end" and node_id:
            ok = (event.payload or {}).get("ok", True)
            status[node_id] = "succeeded" if ok else "failed"
        elif event.type == "gate.fail" and node_id:
            status[node_id] = "running"
        elif event.type == "interrupt":
            status["plan"] = "succeeded"
    return status


class CraftJobStartResponse(BaseModel):
    job: CraftJobResponse
    turn_id: UUID | None = None


class SpecialistCreateItem(BaseModel):
    role: str
    prompt: str


class SpecialistsCreateRequest(BaseModel):
    specialists: list[SpecialistCreateItem]
    project_id: UUID | None = None


class CraftJobResumeRequest(BaseModel):
    action: str = "approve"
    note: str | None = None


class QuestionAskDecisionRequest(BaseModel):
    allow: bool = True
    answer: str | None = None
    answers: list[list[str]] | None = None
