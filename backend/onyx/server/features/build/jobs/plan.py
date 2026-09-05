"""Validated long-job plan object. Disk ``PLAN.json`` is the source."""

from __future__ import annotations

import json
from typing import Any, Final

from pydantic import BaseModel, Field, field_validator

PLAN_JSON_PATH: Final[str] = "outputs/plan/PLAN.json"
SPECIALIST_OUTPUT_PREFIX: Final[str] = "project/research/"
LANE_DONE_FILENAME: Final[str] = "FINDINGS.md"


def _safe_relpath(path: str) -> str:
    cleaned = path.strip().replace("\\", "/").lstrip("/")
    if not cleaned or ".." in cleaned.split("/"):
        raise ValueError(f"Unsafe plan path: {path}")
    return cleaned


class JobPlanLane(BaseModel):
    role: str
    questions: list[str] = Field(default_factory=list)
    output_dir: str

    @field_validator("role")
    @classmethod
    def _role(cls, value: str) -> str:
        role = value.strip().lower().replace(" ", "_")
        if not role:
            raise ValueError("lane role is required")
        return role

    @field_validator("output_dir")
    @classmethod
    def _output_dir(cls, value: str) -> str:
        path = _safe_relpath(value)
        if not path.startswith(SPECIALIST_OUTPUT_PREFIX):
            raise ValueError(
                f"lane output_dir must start with {SPECIALIST_OUTPUT_PREFIX}"
            )
        return path.rstrip("/")

    def done_path(self) -> str:
        return f"{self.output_dir}/{LANE_DONE_FILENAME}"


class JobPlanPhase(BaseModel):
    id: str
    kind: str = "work"
    name: str | None = None
    done_when: list[str] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def _id(cls, value: str) -> str:
        phase_id = value.strip()
        if not phase_id:
            raise ValueError("phase id is required")
        return phase_id

    @field_validator("done_when")
    @classmethod
    def _done_when(cls, value: list[str]) -> list[str]:
        return [_safe_relpath(item) for item in value]


class JobPlan(BaseModel):
    goal: str
    phases: list[JobPlanPhase]
    lanes: list[JobPlanLane] = Field(default_factory=list)
    inputs: list[str] = Field(default_factory=list)

    @field_validator("goal")
    @classmethod
    def _goal(cls, value: str) -> str:
        goal = value.strip()
        if not goal:
            raise ValueError("goal is required")
        return goal

    @field_validator("phases")
    @classmethod
    def _phases(cls, value: list[JobPlanPhase]) -> list[JobPlanPhase]:
        if not value:
            raise ValueError("at least one phase is required")
        return value

    @field_validator("inputs")
    @classmethod
    def _inputs(cls, value: list[str]) -> list[str]:
        return [_safe_relpath(item) for item in value]


def parse_plan(raw: Any) -> JobPlan:
    if not isinstance(raw, dict):
        raise ValueError("plan must be a JSON object")
    plan = JobPlan.model_validate(raw)
    work_phases = [phase for phase in plan.phases if phase.kind == "work"]
    for phase in work_phases:
        if not phase.done_when and not plan.lanes:
            raise ValueError(f"work phase {phase.id} needs done_when or lanes")
    return plan


def parse_plan_bytes(raw: bytes) -> JobPlan:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("PLAN.json is not valid JSON") from exc
    return parse_plan(payload)


def default_done_when(phase_id: str) -> list[str]:
    if phase_id == "plan":
        return [PLAN_JSON_PATH, "outputs/plan/PHASE_DONE"]
    if phase_id == "ingest":
        return ["outputs/ingest/MANIFEST.json", "outputs/plan/PHASE_DONE"]
    if phase_id == "compose":
        return ["outputs/markdown/report.md", "outputs/plan/PHASE_DONE"]
    if phase_id == "review":
        return ["outputs/markdown/report.md", "outputs/plan/PHASE_DONE"]
    return ["outputs/plan/PHASE_DONE"]


def lane_done_paths(plan: JobPlan) -> list[str]:
    return [lane.done_path() for lane in plan.lanes]


def apply_plan_to_job_phases(
    job_phases: list[dict[str, Any]], plan: JobPlan
) -> list[dict[str, Any]]:
    """Copy ``done_when`` from disk onto the job graph. Add lane files."""
    planned = {phase.id: phase for phase in plan.phases}
    lane_paths = lane_done_paths(plan)
    updated: list[dict[str, Any]] = []
    for existing in job_phases:
        clone = dict(existing)
        phase_id = str(clone.get("id") or "")
        match = planned.get(phase_id)
        done_when = (
            list(match.done_when)
            if match and match.done_when
            else list(clone.get("done_when") or default_done_when(phase_id))
        )
        kind = str(clone.get("kind") or "")
        if lane_paths and kind in {"research", "analyze", "work"}:
            for path in lane_paths:
                if path not in done_when:
                    done_when.append(path)
        clone["done_when"] = done_when
        updated.append(clone)
    return updated
