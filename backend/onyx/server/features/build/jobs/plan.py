"""Validated long-job plan object. Disk ``PLAN.json`` is the source."""

from __future__ import annotations

import json
from typing import Any, Final

from pydantic import BaseModel, Field, field_validator, model_validator

from onyx.server.features.build.configs import CRAFT_DEEP_JOB_MAX_SPECIALISTS

PLAN_JSON_PATH: Final[str] = "outputs/plan/PLAN.json"
PLAN_MD_PATH: Final[str] = "outputs/PLAN.md"
TODO_MD_PATH: Final[str] = "outputs/TODO.md"
MEMORY_MD_PATH: Final[str] = "outputs/MEMORY.md"
DONE_JSON_PATH: Final[str] = "outputs/DONE.json"
REVIEW_JSON_PATH: Final[str] = "outputs/review/REVIEW.json"
MANIFEST_PATH: Final[str] = "outputs/ingest/MANIFEST.json"
CANONICAL_LANE_PREFIX: Final[str] = "outputs/lanes/"
ALLOWED_LANE_ROOTS: Final[tuple[str, ...]] = ("outputs/", "project/")
BLOCKED_LANE_PREFIXES: Final[tuple[str, ...]] = (
    "outputs/tmp/",
    "outputs/.venv",
    "outputs/commands/",
    "outputs/mcp/",
    "outputs/plan/",
)
LANE_DONE_FILENAME: Final[str] = "NOTES.md"


def _looks_like_relpath(path: str) -> bool:
    cleaned = path.strip().replace("\\", "/")
    if not cleaned or " " in cleaned or ".." in cleaned.split("/"):
        return False
    return "/" in cleaned


def _reject_escapes(value: Any) -> None:
    texts: list[str] = []
    if isinstance(value, str):
        texts = [value]
    elif isinstance(value, list):
        texts = [item for item in value if isinstance(item, str)]
    for text in texts:
        cleaned = text.strip().replace("\\", "/")
        if ".." in cleaned.split("/"):
            raise ValueError(f"Unsafe plan path: {text}")


def _coerce_path_list(value: Any) -> list[str]:
    _reject_escapes(value)
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if _looks_like_relpath(text) else []
    if isinstance(value, list):
        return [
            item.strip()
            for item in value
            if isinstance(item, str) and _looks_like_relpath(item)
        ]
    return []


def _safe_relpath(path: str) -> str:
    cleaned = path.strip().replace("\\", "/").lstrip("/")
    if not cleaned or ".." in cleaned.split("/"):
        raise ValueError(f"Unsafe plan path: {path}")
    return cleaned


def _dir_of(path: str) -> str:
    cleaned = path.rstrip("/")
    if "/" not in cleaned:
        return f"{CANONICAL_LANE_PREFIX}{cleaned}" if cleaned else CANONICAL_LANE_PREFIX
    return cleaned.rsplit("/", 1)[0]


def _builtin_skill_ids() -> set[str]:
    try:
        from onyx.skills.built_in import BUILT_IN_SKILLS

        return set(BUILT_IN_SKILLS)
    except Exception:
        return set()


def _lane_dir_allowed(path: str) -> bool:
    if not path.startswith(ALLOWED_LANE_ROOTS):
        return False
    for blocked in BLOCKED_LANE_PREFIXES:
        if path == blocked.rstrip("/") or path.startswith(blocked):
            return False
    return True


class JobPlanLane(BaseModel):
    role: str
    questions: list[str] = Field(default_factory=list)
    output_dir: str = ""
    skill_id: str | None = None
    done_when: list[str] = Field(default_factory=list)

    @field_validator("role")
    @classmethod
    def _role(cls, value: str) -> str:
        role = value.strip().lower().replace(" ", "_")
        if not role:
            raise ValueError("lane role is required")
        return role

    @field_validator("skill_id")
    @classmethod
    def _skill_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        skill_id = value.strip()
        return skill_id or None

    @field_validator("done_when", mode="before")
    @classmethod
    def _done_when(cls, value: Any) -> list[str]:
        return [_safe_relpath(item) for item in _coerce_path_list(value)]

    @model_validator(mode="after")
    def _output_dir(self) -> JobPlanLane:
        raw = self.output_dir.strip() if self.output_dir else ""
        if raw:
            path = _safe_relpath(raw)
        elif self.done_when:
            path = _dir_of(self.done_when[0])
        else:
            path = f"{CANONICAL_LANE_PREFIX}{self.role}"
        if not _lane_dir_allowed(path):
            raise ValueError(
                "lane output_dir must be under outputs/ or project/, "
                "and not tmp, .venv, commands, mcp, or plan"
            )
        self.output_dir = path.rstrip("/")
        if not self.skill_id and self.role in _builtin_skill_ids():
            self.skill_id = self.role
        return self

    def done_path(self) -> str:
        if self.done_when:
            return self.done_when[0]
        return f"{self.output_dir}/{LANE_DONE_FILENAME}"

    def required_paths(self) -> list[str]:
        if self.done_when:
            return list(self.done_when)
        return [self.done_path()]


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

    @field_validator("done_when", mode="before")
    @classmethod
    def _done_when(cls, value: Any) -> list[str]:
        return [_safe_relpath(item) for item in _coerce_path_list(value)]


class JobPlan(BaseModel):
    goal: str
    phases: list[JobPlanPhase] = Field(
        default_factory=lambda: [JobPlanPhase(id="plan", kind="plan")]
    )
    lanes: list[JobPlanLane] = Field(default_factory=list)
    inputs: list[str] = Field(default_factory=list)
    ask_delivery: bool = False
    done_when: list[str] = Field(default_factory=list)

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
            return [JobPlanPhase(id="plan", kind="plan")]
        return value

    @field_validator("lanes")
    @classmethod
    def _lanes(cls, value: list[JobPlanLane]) -> list[JobPlanLane]:
        if len(value) > CRAFT_DEEP_JOB_MAX_SPECIALISTS:
            raise ValueError(
                f"at most {CRAFT_DEEP_JOB_MAX_SPECIALISTS} lanes are allowed"
            )
        return value

    @field_validator("inputs")
    @classmethod
    def _inputs(cls, value: list[str]) -> list[str]:
        return [_safe_relpath(item) for item in value]

    @field_validator("done_when", mode="before")
    @classmethod
    def _job_done_when(cls, value: Any) -> list[str]:
        return [_safe_relpath(item) for item in _coerce_path_list(value)]

    def wants_ingest(self) -> bool:
        if self.inputs:
            return True
        return any(phase.kind == "ingest" or phase.id == "ingest" for phase in self.phases)


def parse_plan(raw: Any) -> JobPlan:
    if not isinstance(raw, dict):
        raise ValueError("plan must be a JSON object")
    return JobPlan.model_validate(raw)


def parse_plan_bytes(raw: bytes) -> JobPlan:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("PLAN.json is not valid JSON") from exc
    return parse_plan(payload)


def default_done_when(phase_id: str, kind: str = "") -> list[str]:
    resolved = (kind or phase_id).strip().lower()
    if phase_id == "plan" or resolved == "plan":
        return [PLAN_JSON_PATH, PLAN_MD_PATH, TODO_MD_PATH]
    if phase_id == "ingest" or resolved == "ingest":
        return [MANIFEST_PATH]
    if resolved == "review":
        return [REVIEW_JSON_PATH]
    return []


def lane_done_paths(plan: JobPlan) -> list[str]:
    return [lane.done_path() for lane in plan.lanes]


def apply_plan_to_job_phases(
    job_phases: list[dict[str, Any]], plan: JobPlan
) -> list[dict[str, Any]]:
    """Copy ``done_when`` from disk onto matching job phases."""
    planned = {phase.id: phase for phase in plan.phases}
    updated: list[dict[str, Any]] = []
    for existing in job_phases:
        clone = dict(existing)
        phase_id = str(clone.get("id") or "")
        kind = str(clone.get("kind") or "")
        match = planned.get(phase_id)
        if match and match.done_when:
            clone["done_when"] = list(match.done_when)
        else:
            clone["done_when"] = list(
                clone.get("done_when") or default_done_when(phase_id, kind)
            )
        updated.append(clone)
    return updated
