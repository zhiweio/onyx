"""Host-owned job state channels and reducers.

Progress lives here, not in a mutable phases list. Parallel writes merge
through reducers. Disk holds large objects; channels hold indexes and
summaries.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from onyx.server.features.build.jobs.plan import JobPlan


def strip_postgres_json_nuls(value: Any) -> Any:
    """Postgres JSONB rejects ``\\u0000``. Drop NUL from dumped job state."""
    if isinstance(value, str):
        return value.replace("\x00", "")
    if isinstance(value, list):
        return [strip_postgres_json_nuls(item) for item in value]
    if isinstance(value, dict):
        return {key: strip_postgres_json_nuls(item) for key, item in value.items()}
    return value


class TodoItem(BaseModel):
    id: str
    owner_node: str
    status: Literal["pending", "running", "succeeded", "failed"] = "pending"
    blocking_reason: str | None = None
    title: str = ""


class ArtifactRecord(BaseModel):
    path: str
    schema_name: str | None = None
    hash: str | None = None
    producer_node: str = ""
    summary: str = ""
    cite_ids: list[str] = Field(default_factory=list)
    nonempty: bool = True

    @field_validator("summary", mode="before")
    @classmethod
    def _summary(cls, value: Any) -> str:
        text = "" if value is None else str(value)
        return text.replace("\x00", "")


class CitationRecord(BaseModel):
    key: str
    title: str = ""
    source: str = ""
    number: int | None = None


class ConflictRecord(BaseModel):
    kind: str
    detail: str
    paths: list[str] = Field(default_factory=list)
    owner_node: str | None = None


class BudgetState(BaseModel):
    seconds: float = 0
    tokens: int = 0
    node_attempts: int = 0


class InterruptPayload(BaseModel):
    kind: Literal["approve_plan", "approve_delivery", "clarify"]
    payload: dict[str, Any] = Field(default_factory=dict)


class PlanChannel(BaseModel):
    version: int
    goal: str
    phases: list[dict[str, Any]] = Field(default_factory=list)
    lanes: list[dict[str, Any]] = Field(default_factory=list)
    inputs: list[str] = Field(default_factory=list)
    done_when: dict[str, list[str]] = Field(default_factory=dict)
    ask_delivery: bool = False
    goal_done_when: list[str] = Field(default_factory=list)

    @classmethod
    def from_job_plan(cls, plan: JobPlan, *, version: int) -> "PlanChannel":
        return cls(
            version=version,
            goal=plan.goal,
            phases=[phase.model_dump() for phase in plan.phases],
            lanes=[lane.model_dump() for lane in plan.lanes],
            inputs=list(plan.inputs),
            done_when={phase.id: list(phase.done_when) for phase in plan.phases},
            ask_delivery=plan.ask_delivery,
            goal_done_when=list(plan.done_when),
        )


class JobState(BaseModel):
    goal: str = ""
    plan: PlanChannel | None = None
    todo: dict[str, TodoItem] = Field(default_factory=dict)
    artifacts: dict[str, ArtifactRecord] = Field(default_factory=dict)
    citations: dict[str, CitationRecord] = Field(default_factory=dict)
    conflicts: list[ConflictRecord] = Field(default_factory=list)
    budget: BudgetState = Field(default_factory=BudgetState)
    interrupt: InterruptPayload | None = None
    cursor: list[str] = Field(default_factory=list)
    completed_nodes: list[str] = Field(default_factory=list)
    node_attempts: dict[str, int] = Field(default_factory=dict)
    pending_enqueue: str | None = None
    last_node: str | None = None
    graph: dict[str, Any] | None = None
    drain_reason: str | None = None
    step: int = 0
    paused_seconds: float = 0
    pause_started_at: str | None = None


def empty_state() -> JobState:
    return JobState()


def apply_writes(state: JobState, writes: dict[str, Any]) -> JobState:
    """Apply a delta of channel writes through their reducers."""
    next_state = state.model_copy(deep=True)
    if "goal" in writes:
        next_state.goal = str(writes["goal"] or "")
    if "plan" in writes:
        next_state.plan = _reduce_plan(next_state.plan, writes["plan"])
    if "todo" in writes:
        next_state.todo = _reduce_todo(next_state.todo, writes["todo"])
    if "artifacts" in writes:
        next_state.artifacts = _reduce_artifacts(
            next_state.artifacts, writes["artifacts"]
        )
    if "citations" in writes:
        next_state.citations = _reduce_citations(
            next_state.citations, writes["citations"]
        )
    if "conflicts" in writes:
        next_state.conflicts = _reduce_conflicts(
            next_state.conflicts, writes["conflicts"]
        )
    if "budget" in writes:
        next_state.budget = _reduce_budget(next_state.budget, writes["budget"])
    if "interrupt" in writes:
        raw = writes["interrupt"]
        next_state.interrupt = (
            None if raw is None else InterruptPayload.model_validate(raw)
        )
    if "cursor" in writes:
        next_state.cursor = [str(item) for item in writes["cursor"] or []]
    if "completed_nodes" in writes:
        next_state.completed_nodes = _reduce_completed(
            next_state.completed_nodes, writes["completed_nodes"]
        )
    if "reopen_nodes" in writes:
        remove = {str(item) for item in writes["reopen_nodes"] or []}
        next_state.completed_nodes = [
            item for item in next_state.completed_nodes if item not in remove
        ]
    if "node_attempts" in writes:
        next_state.node_attempts = {
            **next_state.node_attempts,
            **{str(key): int(value) for key, value in writes["node_attempts"].items()},
        }
    if "pending_enqueue" in writes:
        pending = writes["pending_enqueue"]
        next_state.pending_enqueue = None if pending is None else str(pending)
    if "last_node" in writes:
        last = writes["last_node"]
        next_state.last_node = None if last is None else str(last)
    if "graph" in writes:
        graph = writes["graph"]
        next_state.graph = None if graph is None else dict(graph)
    if "drain_reason" in writes:
        reason = writes["drain_reason"]
        next_state.drain_reason = None if reason is None else str(reason)
    if "step" in writes:
        next_state.step = int(writes["step"])
    if "paused_seconds" in writes:
        next_state.paused_seconds = float(writes["paused_seconds"] or 0)
    if "pause_started_at" in writes:
        raw_pause = writes["pause_started_at"]
        next_state.pause_started_at = None if raw_pause is None else str(raw_pause)
    return next_state


def migrate_from_phases(
    phases: list[dict[str, Any]],
    current_index: int,
    *,
    domain: str,
    goal: str,
) -> JobState:
    """Lift a pre-kernel job into channels. Old list jobs stay readable."""
    from onyx.server.features.build.jobs.graph import compile_graph

    graph = compile_graph(domain)
    completed: list[str] = []
    cursor: list[str] = []
    for index, phase in enumerate(phases or []):
        phase_id = str(phase.get("id") or "")
        if not phase_id:
            continue
        status = str(phase.get("status") or "pending")
        if status == "succeeded":
            completed.append(phase_id)
        elif index == current_index or status == "running":
            cursor.append(phase_id)
    if not cursor and 0 <= current_index < len(phases or []):
        cursor = [str((phases[current_index] or {}).get("id") or "plan")]
    if not cursor:
        cursor = ["plan"]
    return JobState(
        goal=goal,
        cursor=cursor,
        completed_nodes=completed,
        graph=graph.to_snapshot(),
    )


def _reduce_plan(current: PlanChannel | None, incoming: Any) -> PlanChannel:
    incoming_plan = PlanChannel.model_validate(incoming)
    if current is not None and incoming_plan.version <= current.version:
        raise ValueError("new plan must increase version")
    return incoming_plan


def _reduce_todo(current: dict[str, TodoItem], incoming: Any) -> dict[str, TodoItem]:
    result = dict(current)
    if not isinstance(incoming, dict):
        return result
    for key, value in incoming.items():
        item = TodoItem.model_validate(value)
        existing = result.get(item.id) or result.get(str(key))
        if existing is not None and existing.status == "succeeded":
            if item.status != "succeeded":
                continue
        result[item.id] = item
    return result


def _reduce_artifacts(
    current: dict[str, ArtifactRecord], incoming: Any
) -> dict[str, ArtifactRecord]:
    result = dict(current)
    if not isinstance(incoming, dict):
        return result
    for path, value in incoming.items():
        record = ArtifactRecord.model_validate(value)
        result[record.path or str(path)] = record
    return result


def _reduce_citations(
    current: dict[str, CitationRecord], incoming: Any
) -> dict[str, CitationRecord]:
    result = dict(current)
    if not isinstance(incoming, dict):
        return result
    for key, value in incoming.items():
        record = CitationRecord.model_validate(value)
        result[record.key or str(key)] = record
    numbers = sorted(
        (item.number for item in result.values() if item.number is not None)
    )
    next_number = (numbers[-1] + 1) if numbers else 1
    for record in result.values():
        if record.number is None:
            record.number = next_number
            next_number += 1
    return result


def _reduce_conflicts(
    current: list[ConflictRecord], incoming: Any
) -> list[ConflictRecord]:
    extra: list[ConflictRecord] = []
    if isinstance(incoming, list):
        extra = [ConflictRecord.model_validate(item) for item in incoming]
    return [*current, *extra]


def _reduce_budget(current: BudgetState, incoming: Any) -> BudgetState:
    delta = incoming if isinstance(incoming, dict) else {}
    return BudgetState(
        seconds=current.seconds + float(delta.get("seconds") or 0),
        tokens=current.tokens + int(delta.get("tokens") or 0),
        node_attempts=current.node_attempts + int(delta.get("node_attempts") or 0),
    )


def _reduce_completed(current: list[str], incoming: Any) -> list[str]:
    extra = [str(item) for item in incoming or []]
    seen = set(current)
    result = list(current)
    for item in extra:
        if item not in seen:
            result.append(item)
            seen.add(item)
    return result
