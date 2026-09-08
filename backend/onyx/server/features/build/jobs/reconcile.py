"""Join research lanes: citations, conflicts, coverage."""

from __future__ import annotations

import json
import re
from typing import Any
from uuid import UUID

from onyx.server.features.build.jobs.channels import (
    CitationRecord,
    ConflictRecord,
    JobState,
)
from onyx.server.features.build.jobs.graph import GraphNode
from onyx.server.features.build.jobs.plan import JobPlanLane
from onyx.server.features.build.sandbox.factory import get_sandbox_manager

RECONCILE_PATH = "outputs/reconcile/RECONCILE.json"
BLACKBOARD_PATH = "outputs/reconcile/BLACKBOARD.md"
_CITE_RE = re.compile(r"\[(\d+)\]|\(([^)]+\.\w{2,4})\)|https?://\S+")
_UNANSWERED_HEADING = re.compile(
    r"^#{1,6}\s+(unanswered|open questions|gaps)\b", re.IGNORECASE | re.MULTILINE
)


def reconcile_lanes(
    *,
    sandbox_id: UUID,
    session_id: UUID,
    state: JobState,
    lane_nodes: list[GraphNode],
) -> tuple[dict[str, Any], dict[str, CitationRecord], list[ConflictRecord]]:
    manager = get_sandbox_manager()
    citations: dict[str, CitationRecord] = dict(state.citations)
    conflicts: list[ConflictRecord] = []
    covered = 0
    asked = 0
    lane_summaries: list[dict[str, Any]] = []

    for node in lane_nodes:
        path = node.required_paths[0] if node.required_paths else ""
        text = _read_text(manager, sandbox_id, session_id, path)
        questions = _lane_questions(state, node.role)
        asked += len(questions)
        hits = _answered_questions(text or "", questions)
        covered += hits
        if text:
            for key, title in _extract_citations(text):
                citations.setdefault(
                    key,
                    CitationRecord(key=key, title=title, source=path),
                )
        if questions and hits < len(questions):
            conflicts.append(
                ConflictRecord(
                    kind="coverage",
                    detail=f"{node.id} answered {hits}/{len(questions)} questions",
                    paths=[path] if path else [],
                    owner_node=node.id,
                )
            )
        lane_summaries.append(
            {
                "node_id": node.id,
                "role": node.role,
                "path": path,
                "answered": hits,
                "asked": len(questions),
            }
        )

    coverage = (covered / asked) if asked else 1.0
    numbered = _renumber(citations)
    payload = {
        "coverage": coverage,
        "lanes": lane_summaries,
        "citation_count": len(numbered),
        "conflicts": [item.model_dump() for item in conflicts],
    }
    return payload, numbered, conflicts


def write_reconcile_file(
    *,
    sandbox_id: UUID,
    session_id: UUID,
    payload: dict[str, Any],
) -> None:
    raw = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    _write_files(
        sandbox_id=sandbox_id,
        session_id=session_id,
        files={RECONCILE_PATH: raw},
    )


def write_blackboard_file(
    *,
    sandbox_id: UUID,
    session_id: UUID,
    payload: dict[str, Any],
) -> None:
    _write_files(
        sandbox_id=sandbox_id,
        session_id=session_id,
        files={BLACKBOARD_PATH: _blackboard_markdown(payload).encode("utf-8")},
    )


def _blackboard_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Reconcile blackboard",
        "",
        f"Coverage: {payload.get('coverage')}",
        f"Citations: {payload.get('citation_count')}",
        "",
        "## Lanes",
    ]
    for lane in payload.get("lanes") or []:
        if not isinstance(lane, dict):
            continue
        lines.extend(
            [
                f"### {lane.get('role') or lane.get('node_id')}",
                f"Path: {lane.get('path')}",
                f"Answered: {lane.get('answered')}/{lane.get('asked')}",
                "",
            ]
        )
    lines.append("## Conflicts")
    conflicts = payload.get("conflicts") or []
    if not conflicts:
        lines.append("None.")
    for item in conflicts:
        if isinstance(item, dict):
            lines.append(f"- {item.get('kind')}: {item.get('detail')}")
        else:
            lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def _write_files(
    *,
    sandbox_id: UUID,
    session_id: UUID,
    files: dict[str, bytes],
) -> None:
    manager = get_sandbox_manager()
    try:
        manager.write_files_to_sandbox(
            sandbox_id=sandbox_id,
            mount_path=_session_mount(session_id),
            files=files,
        )
    except Exception:
        return


def default_lane(role: str) -> JobPlanLane:
    return JobPlanLane(role=role)


def _lane_questions(state: JobState, role: str | None) -> list[str]:
    if state.plan is None or not role:
        return []
    for lane in state.plan.lanes:
        if str(lane.get("role") or "") == role:
            raw = lane.get("questions") or []
            return [str(item) for item in raw]
    return []


def _answered_questions(text: str, questions: list[str]) -> int:
    if not text or not questions:
        return 0
    working = _text_without_unanswered(text)
    return sum(1 for question in questions if _question_mentioned(working, question))


def _text_without_unanswered(text: str) -> str:
    match = _UNANSWERED_HEADING.search(text)
    if match is None:
        return text
    return text[: match.start()]


def _question_mentioned(text: str, question: str) -> bool:
    lowered = text.lower()
    query = question.lower().strip()
    if not query:
        return False
    if query in lowered:
        return True
    words = [word for word in re.split(r"\W+", query) if word]
    if len(words) >= 4 and " ".join(words[:4]) in lowered:
        return True
    return False


def _extract_citations(text: str) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for match in _CITE_RE.finditer(text):
        token = match.group(1) or match.group(2) or ""
        if token:
            found.append((token, token))
    return found


def _renumber(
    citations: dict[str, CitationRecord],
) -> dict[str, CitationRecord]:
    numbered: dict[str, CitationRecord] = {}
    for index, (key, record) in enumerate(sorted(citations.items()), start=1):
        numbered[key] = record.model_copy(update={"number": index})
    return numbered


def _read_text(manager: object, sandbox_id: UUID, session_id: UUID, path: str) -> str:
    if not path:
        return ""
    try:
        raw = manager.read_file(sandbox_id, session_id, path)  # type: ignore[attr-defined]
    except Exception:
        return ""
    if not isinstance(raw, (bytes, bytearray)):
        return ""
    return raw.decode("utf-8", errors="replace")


def _session_mount(session_id: UUID) -> str:
    return f"/workspace/sessions/{session_id}"
