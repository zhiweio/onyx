"""Cross-domain file layout and phase prompts for Craft long jobs."""

from __future__ import annotations

from typing import Any, Final

PHASE_DONE_PATH: Final[str] = "outputs/plan/PHASE_DONE"
PLAN_PATH: Final[str] = "outputs/plan/PLAN.md"
TODO_PATH: Final[str] = "outputs/plan/TODO.json"
MANIFEST_PATH: Final[str] = "outputs/ingest/MANIFEST.json"

DOCUMENT_PHASES: Final[tuple[dict[str, str], ...]] = (
    {"id": "plan", "name": "Plan", "kind": "plan"},
    {"id": "ingest", "name": "Ingest documents", "kind": "ingest"},
    {"id": "analyze", "name": "Analyze", "kind": "analyze"},
    {"id": "compose", "name": "Compose report", "kind": "compose"},
    {"id": "review", "name": "Review", "kind": "review"},
)

RESEARCH_PHASES: Final[tuple[dict[str, str], ...]] = (
    {"id": "plan", "name": "Plan", "kind": "plan"},
    {"id": "research", "name": "Research", "kind": "research"},
    {"id": "compose", "name": "Compose report", "kind": "compose"},
    {"id": "review", "name": "Review", "kind": "review"},
)

RESEARCH_DOMAINS: Final[frozenset[str]] = frozenset({"biomed"})

DEFAULT_SPECIALIST_ROLES: Final[dict[str, tuple[str, ...]]] = {
    "biomed": ("literature", "clinical", "patent", "cmc"),
    "tax": ("xlsx_parser", "pdf_vision", "reconcilier", "exception_writer"),
    "general": ("ingest", "analyze", "exception_writer"),
}


def default_phases_for_domain(domain: str) -> list[dict[str, Any]]:
    source = RESEARCH_PHASES if domain in RESEARCH_DOMAINS else DOCUMENT_PHASES
    return [{**phase, "status": "pending"} for phase in source]


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
    found = phase_index_by_id(job_phases, "compose")
    if found is not None:
        return found
    return max(0, len(job_phases) - 1)


def continuation_prompt(*, phase: dict[str, Any], domain: str, job_name: str) -> str:
    phase_id = str(phase.get("id") or "plan")
    phase_name = str(phase.get("name") or phase_id)
    return (
        f"Continue the long job `{job_name}` ({domain}).\n"
        f"You are starting phase `{phase_id}` ({phase_name}).\n"
        "Read `outputs/plan/PLAN.md` and `outputs/plan/TODO.json` first. "
        "Read only the input files this phase needs. "
        "Do not restart finished phases. "
        "Extract tables with the document-ingest skill; never load a whole "
        "workbook into chat. Write large MCP and extract results to disk and "
        "reply with a digest plus the path.\n"
        f"When this phase meets its done-when, write `{PHASE_DONE_PATH}` "
        f"with the single line `{phase_id}` and stop."
    )


def first_phase_prompt(*, user_prompt: str, domain: str, job_name: str) -> str:
    return (
        f"Start the long job `{job_name}` ({domain}).\n"
        "Follow `long-job-protocol`. Create `outputs/plan/PLAN.md` and "
        "`outputs/plan/TODO.json` if they are missing.\n"
        "User request:\n"
        f"{user_prompt.strip()}\n"
        f"When the plan phase is done, write `{PHASE_DONE_PATH}` with the "
        "single line `plan` and stop."
    )


def specialist_prompt(*, role: str, user_prompt: str, job_name: str) -> str:
    return (
        f"You are the `{role}` specialist for long job `{job_name}`.\n"
        "Work only on this role. Write findings under "
        f"`project/research/{role}/` and extracted tables under "
        "`project/extracted/` or `outputs/extracted/`. "
        "Cite source file paths. Do not compose the final report.\n"
        f"{user_prompt.strip()}"
    )
