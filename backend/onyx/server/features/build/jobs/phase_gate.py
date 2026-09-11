"""Decide whether a long-job phase may advance."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from onyx.server.features.build.jobs.durability import (
    is_durability_control_path,
    is_substantial_durability_text,
)
from onyx.server.features.build.jobs.plan import default_done_when
from onyx.server.features.build.jobs.protocol import PHASE_DONE_PATH
from onyx.server.features.build.sandbox.factory import get_sandbox_manager

DEFAULT_PHASE_RETRY_LIMIT = 3
PENDING_ENQUEUE_PROMPT_KEY = "pending_enqueue_prompt"


@dataclass(frozen=True)
class PhaseGateResult:
    passed: bool
    missing: list[str]
    phase_id: str
    retries: int


def evaluate_phase_gate(
    *,
    sandbox_id: UUID,
    session_id: UUID,
    phase: dict[str, Any],
    deadline_exceeded: bool,
    retry_limit: int = DEFAULT_PHASE_RETRY_LIMIT,
) -> PhaseGateResult:
    phase_id = str(phase.get("id") or "")
    retries = int(phase.get("gate_retries") or 0)
    if deadline_exceeded:
        return PhaseGateResult(
            passed=False,
            missing=["turn deadline exceeded"],
            phase_id=phase_id,
            retries=retries,
        )
    if retries >= retry_limit and not _phase_artifacts_ready(
        sandbox_id, session_id, phase
    ):
        return PhaseGateResult(
            passed=False,
            missing=list(phase.get("done_when") or default_done_when(phase_id)),
            phase_id=phase_id,
            retries=retries,
        )
    missing = _missing_paths(sandbox_id, session_id, phase)
    return PhaseGateResult(
        passed=not missing,
        missing=missing,
        phase_id=phase_id,
        retries=retries,
    )


def retry_prompt(phase_id: str, missing: list[str]) -> str:
    from onyx.server.features.build.jobs.gates import retry_brief

    return retry_brief(phase_id, missing)


def increment_gate_retries(phase: dict[str, Any]) -> int:
    next_count = int(phase.get("gate_retries") or 0) + 1
    phase["gate_retries"] = next_count
    return next_count


def set_pending_enqueue_prompt(phase: dict[str, Any], prompt: str) -> None:
    phase[PENDING_ENQUEUE_PROMPT_KEY] = prompt


def pop_pending_enqueue_prompt(phase: dict[str, Any]) -> str | None:
    raw = phase.pop(PENDING_ENQUEUE_PROMPT_KEY, None)
    if not isinstance(raw, str) or not raw.strip():
        return None
    return raw


def _phase_artifacts_ready(
    sandbox_id: UUID, session_id: UUID, phase: dict[str, Any]
) -> bool:
    return not _missing_paths(sandbox_id, session_id, phase)


def _missing_paths(
    sandbox_id: UUID, session_id: UUID, phase: dict[str, Any]
) -> list[str]:
    phase_id = str(phase.get("id") or "")
    done_when = list(phase.get("done_when") or default_done_when(phase_id))
    missing: list[str] = []
    done_line = _read_text(sandbox_id, session_id, PHASE_DONE_PATH)
    if done_line != phase_id:
        missing.append(PHASE_DONE_PATH)
    for path in done_when:
        if path == PHASE_DONE_PATH:
            continue
        if is_durability_control_path(path):
            if not is_substantial_durability_text(
                _read_file_text(sandbox_id, session_id, path), path
            ):
                missing.append(path)
            continue
        if not _path_exists(sandbox_id, session_id, path):
            missing.append(path)
    return missing


def _read_file_text(sandbox_id: UUID, session_id: UUID, path: str) -> str:
    try:
        raw = get_sandbox_manager().read_file(sandbox_id, session_id, path)
    except Exception:
        return ""
    if not isinstance(raw, (bytes, bytearray)):
        return ""
    return raw.decode("utf-8", errors="replace")


def _read_text(sandbox_id: UUID, session_id: UUID, path: str) -> str | None:
    try:
        raw = get_sandbox_manager().read_file(sandbox_id, session_id, path)
    except Exception:
        return None
    text = raw.decode("utf-8", errors="replace").strip()
    if not text:
        return None
    return text.splitlines()[0].strip()


def _path_exists(sandbox_id: UUID, session_id: UUID, path: str) -> bool:
    manager = get_sandbox_manager()
    try:
        manager.read_file(sandbox_id, session_id, path)
        return True
    except Exception:
        pass
    try:
        manager.list_directory(sandbox_id, session_id, path)
        return True
    except Exception:
        return False
