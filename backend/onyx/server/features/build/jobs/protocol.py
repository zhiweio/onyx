"""Cross-domain file layout and phase prompts for Craft long jobs."""

from __future__ import annotations

from typing import Any, Final

from onyx.server.features.build.jobs.plan import (
    DONE_JSON_PATH,
    PLAN_JSON_PATH,
    PLAN_MD_PATH,
    TODO_MD_PATH,
)

PHASE_DONE_PATH: Final[str] = "outputs/plan/PHASE_DONE"
PLAN_PATH: Final[str] = PLAN_MD_PATH
TODO_PATH: Final[str] = TODO_MD_PATH
MANIFEST_PATH: Final[str] = "outputs/ingest/MANIFEST.json"


def infer_job_domain(_prompt: str, explicit: str | None = None) -> str:
    """Label only. Never infer a scene from the prompt."""
    if explicit and explicit.strip():
        return explicit.strip().lower()
    return "general"


def default_phases_for_domain(domain: str) -> list[dict[str, Any]]:
    from onyx.server.features.build.jobs.graph import compile_graph

    return compile_graph(domain).to_phase_list()


def current_phase(
    job_phases: list[dict[str, Any]], index: int
) -> dict[str, Any] | None:
    if index < 0 or index >= len(job_phases):
        return None
    return job_phases[index]


def phase_index_by_id(job_phases: list[dict[str, Any]], phase_id: str) -> int | None:
    for i, phase in enumerate(job_phases):
        if phase.get("id") == phase_id:
            return i
    return None


def compose_phase_index(job_phases: list[dict[str, Any]]) -> int:
    for key in ("work", "compose", "review"):
        found = phase_index_by_id(job_phases, key)
        if found is not None:
            return found
    return max(0, len(job_phases) - 1)


def continuation_prompt(*, phase: dict[str, Any], domain: str, job_name: str) -> str:
    phase_id = str(phase.get("id") or "plan")
    phase_name = str(phase.get("name") or phase_id)
    return (
        f"Continue the long job `{job_name}` ({domain}).\n"
        f"Current node: `{phase_id}` ({phase_name}).\n"
        "Read the living plan and todo on disk if you need them. "
        f"Use {DONE_JSON_PATH} when the goal is met. "
        "Do not start the next node. "
        "The user-visible reply is about their task, not these files."
    )


def first_phase_prompt(*, user_prompt: str, domain: str, job_name: str) -> str:
    return (
        f"Start the long job `{job_name}` ({domain}).\n"
        f"Write `{PLAN_JSON_PATH}` so the host can compile THIS job. "
        "Optional: phases, lanes, inputs, ask_delivery. "
        "Do not assume a report.\n"
        "User request:\n"
        f"{user_prompt.strip()}\n"
        "Stop after the plan node. Do not start later work. "
        "The user-visible reply is about their task, not these files."
    )


def specialist_prompt(*, role: str, user_prompt: str, job_name: str) -> str:
    return (
        f"You are the `{role}` specialist for long job `{job_name}`.\n"
        "Work only on this role. Write notes under this lane directory "
        "as `NOTES.md`. Create `outputs/extracted/` only if you cache a "
        "large extract.\n"
        f"{user_prompt.strip()}"
    )
