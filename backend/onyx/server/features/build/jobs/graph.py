"""Compile a host-owned node graph from the model's PLAN.json only."""

from __future__ import annotations

from typing import Any, Final, Literal, get_args

from pydantic import BaseModel, Field

from onyx.server.features.build.jobs.channels import JobState
from onyx.server.features.build.jobs.plan import (
    DONE_JSON_PATH,
    JobPlan,
    JobPlanLane,
    JobPlanPhase,
    default_done_when,
)

NodeKind = Literal[
    "plan",
    "ingest",
    "analyze",
    "lane",
    "research_lane",
    "reconcile",
    "work",
    "compose",
    "review",
    "revise",
]
WorkerKind = Literal["opencode_turn", "host_pure"]
IsolationKind = Literal["parent_session", "child_session"]
HitlKind = Literal["none", "approve_plan", "approve_delivery"]

LANE_KINDS: Final[frozenset[str]] = frozenset({"lane", "research_lane"})
_KNOWN_KINDS: Final[frozenset[str]] = frozenset(get_args(NodeKind))
_SKIP_PHASE_KINDS: Final[frozenset[str]] = frozenset(
    {"plan", "ingest", "lane", "research_lane"}
)


def is_lane_kind(kind: str) -> bool:
    return kind in LANE_KINDS


class GraphNode(BaseModel):
    id: str
    kind: NodeKind
    name: str
    worker: WorkerKind
    depends_on: list[str] = Field(default_factory=list)
    input_channels: list[str] = Field(default_factory=list)
    output_channels: list[str] = Field(default_factory=list)
    isolation: IsolationKind = "parent_session"
    hitl: HitlKind = "none"
    role: str | None = None
    skill_id: str | None = None
    required_paths: list[str] = Field(default_factory=list)
    join: bool = False
    product_name: str = ""
    success_criteria: str = ""
    forbid: list[str] = Field(default_factory=list)

    def to_phase_dict(self, *, status: str = "pending") -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "status": status,
            "worker": self.worker,
            "hitl": self.hitl,
            "isolation": self.isolation,
            "required_paths": list(self.required_paths),
            "depends_on": list(self.depends_on),
            "role": self.role,
            "skill_id": self.skill_id,
        }


class JobGraph(BaseModel):
    nodes: list[GraphNode]

    def node_map(self) -> dict[str, GraphNode]:
        return {node.id: node for node in self.nodes}

    def get(self, node_id: str) -> GraphNode | None:
        return self.node_map().get(node_id)

    def to_snapshot(self) -> dict[str, Any]:
        return {"nodes": [node.model_dump() for node in self.nodes]}

    def to_phase_list(
        self, *, completed: list[str] | None = None
    ) -> list[dict[str, Any]]:
        done = set(completed or [])
        phases: list[dict[str, Any]] = []
        for node in self.nodes:
            status = "succeeded" if node.id in done else "pending"
            phases.append(node.to_phase_dict(status=status))
        return phases


def compile_graph(_domain: str = "", plan: JobPlan | None = None) -> JobGraph:
    """Build the host graph from the model plan. Domain is a label only."""
    nodes: list[GraphNode] = [_plan_node()]
    if plan is None:
        return JobGraph(nodes=nodes)

    predecessor = "plan"
    if plan.wants_ingest():
        nodes.append(_ingest_node())
        predecessor = "ingest"

    extra = [phase for phase in plan.phases if not _skip_planned_phase(phase)]
    lanes = list(plan.lanes)
    used_ids = {node.id for node in nodes}
    if lanes:
        lane_ids: list[str] = []
        for lane in lanes:
            node = _lane_node(lane, predecessor)
            node = node.model_copy(update={"id": _unique_id(used_ids, node.id)})
            nodes.append(node)
            lane_ids.append(node.id)
        reconcile = _reconcile_node(lane_ids)
        reconcile = reconcile.model_copy(
            update={"id": _unique_id(used_ids, reconcile.id)}
        )
        nodes.append(reconcile)
        predecessor = reconcile.id

    for phase in extra:
        node = _phase_from_plan(phase, predecessor, ask_delivery=plan.ask_delivery)
        node = node.model_copy(update={"id": _unique_id(used_ids, node.id)})
        nodes.append(node)
        predecessor = node.id

    if not extra:
        work = _work_node(
            predecessor,
            required=list(plan.done_when) or [DONE_JSON_PATH],
        )
        work = work.model_copy(update={"id": _unique_id(used_ids, work.id)})
        nodes.append(work)
        predecessor = work.id

    if plan.ask_delivery and not _has_review(nodes):
        review = _review_node(predecessor)
        review = review.model_copy(update={"id": _unique_id(used_ids, review.id)})
        nodes.append(review)
    return JobGraph(nodes=nodes)


def graph_from_snapshot(snapshot: dict[str, Any] | None) -> JobGraph | None:
    if not snapshot or not isinstance(snapshot.get("nodes"), list):
        return None
    return JobGraph.model_validate(snapshot)


def ready_nodes(graph: JobGraph, state: JobState) -> list[GraphNode]:
    completed = set(state.completed_nodes)
    ready: list[GraphNode] = []
    for node in graph.nodes:
        if node.id in completed:
            continue
        if all(dep in completed for dep in node.depends_on):
            ready.append(node)
    return ready


def _unique_id(used: set[str], node_id: str) -> str:
    if node_id not in used:
        used.add(node_id)
        return node_id
    index = 2
    while f"{node_id}-{index}" in used:
        index += 1
    unique = f"{node_id}-{index}"
    used.add(unique)
    return unique


def _has_review(nodes: list[GraphNode]) -> bool:
    return any(node.kind == "review" or node.id == "review" for node in nodes)


def _as_node_kind(kind: str) -> NodeKind:
    cleaned = kind.strip().lower() or "work"
    if cleaned in LANE_KINDS:
        return "lane"
    if cleaned in _KNOWN_KINDS:
        return cleaned  # type: ignore[return-value]
    return "work"


def _skip_planned_phase(phase: JobPlanPhase) -> bool:
    if phase.id in {"plan", "ingest"}:
        return True
    return phase.kind.strip().lower() in _SKIP_PHASE_KINDS


def _plan_node() -> GraphNode:
    return GraphNode(
        id="plan",
        kind="plan",
        name="Plan",
        worker="opencode_turn",
        hitl="none",
        input_channels=["goal"],
        output_channels=["plan", "todo"],
        required_paths=default_done_when("plan"),
        product_name="Job plan",
        success_criteria=(
            "Choose the graph for this job in PLAN.json. Then stop. "
            "Do not start later nodes."
        ),
        forbid=["Do not start later nodes"],
    )


def _ingest_node() -> GraphNode:
    return GraphNode(
        id="ingest",
        kind="ingest",
        name="Ingest",
        worker="host_pure",
        depends_on=["plan"],
        input_channels=["plan"],
        output_channels=["artifacts"],
        required_paths=default_done_when("ingest"),
        product_name="Ingest manifest",
        success_criteria="Parse source files into MANIFEST and extracts.",
        forbid=["Do not start later nodes"],
    )


def _reconcile_node(lane_ids: list[str]) -> GraphNode:
    return GraphNode(
        id="reconcile",
        kind="reconcile",
        name="Reconcile",
        worker="host_pure",
        depends_on=lane_ids,
        join=True,
        input_channels=["artifacts"],
        output_channels=["artifacts", "conflicts"],
        required_paths=["outputs/reconcile/RECONCILE.json"],
        product_name="Lane join",
        success_criteria="Join lane notes, list conflicts, check coverage.",
    )


def _work_node(predecessor: str, *, required: list[str]) -> GraphNode:
    return GraphNode(
        id="work",
        kind="work",
        name="Work",
        worker="opencode_turn",
        depends_on=[predecessor],
        input_channels=["plan", "artifacts"],
        output_channels=["artifacts"],
        required_paths=list(required),
        product_name="Job work",
        success_criteria=(
            "Meet the user goal. Write DONE.json when the goal is met."
        ),
        forbid=["Do not start later nodes"],
    )


def _review_node(predecessor: str) -> GraphNode:
    return GraphNode(
        id="review",
        kind="review",
        name="Review",
        worker="opencode_turn",
        depends_on=[predecessor],
        hitl="approve_delivery",
        input_channels=["plan", "artifacts"],
        output_channels=["interrupt"],
        required_paths=default_done_when("review", "review"),
        product_name="Review verdict",
        success_criteria="Write REVIEW.json with passed and any remaining gaps.",
    )


def _phase_from_plan(
    phase: JobPlanPhase, predecessor: str, *, ask_delivery: bool = False
) -> GraphNode:
    kind = _as_node_kind(phase.kind)
    required = list(phase.done_when) or default_done_when(phase.id, kind)
    is_review = kind == "review" or phase.id == "review"
    hitl: HitlKind = "approve_delivery" if is_review and ask_delivery else "none"
    name = phase.name or phase.id.replace("_", " ").title()
    return GraphNode(
        id=phase.id,
        kind=kind,
        name=name,
        worker="opencode_turn",
        depends_on=[predecessor],
        hitl=hitl,
        input_channels=["plan", "artifacts"],
        output_channels=["artifacts"],
        required_paths=required,
        product_name=name,
        success_criteria="Write the files this node lists, then stop.",
        forbid=["Do not start later nodes"],
    )


def _lane_node(lane: JobPlanLane, predecessor: str) -> GraphNode:
    return GraphNode(
        id=f"lane:{lane.role}",
        kind="lane",
        name=lane.role.replace("_", " ").title(),
        worker="opencode_turn",
        depends_on=[predecessor],
        isolation="child_session",
        role=lane.role,
        skill_id=lane.skill_id,
        input_channels=["plan", "artifacts"],
        output_channels=["artifacts"],
        required_paths=lane.required_paths(),
        product_name=f"{lane.role} notes",
        success_criteria=(
            "Do only this lane. Write NOTES.md under the lane directory. "
            "Do not start other nodes."
        ),
        forbid=["Do not enter another lane", "Do not start later nodes"],
    )
