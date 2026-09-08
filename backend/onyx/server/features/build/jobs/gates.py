"""Contract gates for a graph node. Path existence is one check, not the only one."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from onyx.server.features.build.jobs.graph import GraphNode, is_lane_kind
from onyx.server.features.build.jobs.phase_gate import (
    DEFAULT_PHASE_RETRY_LIMIT,
    _path_exists,
    _read_text,
)
from onyx.server.features.build.jobs.plan import (
    DONE_JSON_PATH,
    PLAN_JSON_PATH,
    REVIEW_JSON_PATH,
    TODO_MD_PATH,
    parse_plan_bytes,
)
from onyx.server.features.build.sandbox.factory import get_sandbox_manager

_LANE_OUT_OF_BOUNDS = (
    DONE_JSON_PATH,
    "outputs/markdown/",
)
_NAMED_SEARCH_HINTS = (
    "parallel search",
    "parallel-search",
    "tavily",
    "exa search",
    "websearch",
    "web search",
)


def named_search_required(text: str) -> bool:
    lowered = (text or "").lower()
    return any(hint in lowered for hint in _NAMED_SEARCH_HINTS)


_OPEN_TODO_RE = re.compile(r"^\s*[-*+]\s*\[\s\]", re.MULTILINE)
_CITATION_RE = re.compile(
    r"https?://|\[[0-9]+\]|\[[A-Za-z][\w.-]{1,}\]",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class GateMissing:
    path: str
    reason: str
    owner_node: str


@dataclass(frozen=True)
class ContractGateResult:
    passed: bool
    missing: list[GateMissing] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    coverage: float | None = None
    review: dict[str, Any] | None = None

    def missing_paths(self) -> list[str]:
        return [item.path for item in self.missing]


def retry_limit_error_detail(*parts: str) -> str:
    detail = ", ".join(part.strip() for part in parts if part and part.strip())
    return f"Phase gate retry limit reached: {detail or 'unknown'}"


def gate_retry_limit_detail(gate: ContractGateResult, node_id: str) -> str:
    paths = [path for path in gate.missing_paths() if path]
    reasons = [item.reason for item in gate.missing if item.reason]
    return retry_limit_error_detail(*(paths or reasons or [node_id]))


def evaluate_contract_gate(
    *,
    sandbox_id: UUID,
    session_id: UUID,
    node: GraphNode,
    deadline_exceeded: bool,
    attempts: int = 0,
    retry_limit: int = DEFAULT_PHASE_RETRY_LIMIT,
    search_required: bool = False,
) -> ContractGateResult:
    if deadline_exceeded:
        return ContractGateResult(
            passed=False,
            missing=[
                GateMissing(
                    path="turn deadline exceeded",
                    reason="turn deadline exceeded",
                    owner_node=node.id,
                )
            ],
        )
    if attempts >= retry_limit:
        return ContractGateResult(
            passed=False,
            missing=[
                GateMissing(
                    path=path,
                    reason="retry limit reached",
                    owner_node=node.id,
                )
                for path in node.required_paths
            ]
            or [
                GateMissing(
                    path=node.id,
                    reason="retry limit reached",
                    owner_node=node.id,
                )
            ],
        )

    missing = _missing_required(sandbox_id, session_id, node)
    if missing:
        return ContractGateResult(passed=False, missing=missing)

    if node.kind == "plan":
        return _gate_plan(sandbox_id, session_id, node)
    if is_lane_kind(node.kind):
        return _gate_lane(
            sandbox_id,
            session_id,
            node,
            search_required=search_required,
        )
    if node.kind == "review":
        return _gate_review(sandbox_id, session_id, node)
    if node.kind in {"work", "analyze", "compose", "revise"}:
        return _gate_work(sandbox_id, session_id, node)
    return ContractGateResult(passed=True)


def retry_brief(
    node_id: str, missing: list[str], reasons: list[str] | None = None
) -> str:
    listed = ", ".join(missing) if missing else "required artifacts"
    reason_bits = [
        item.replace("\n", " ").strip()
        for item in (reasons or [])
        if item and item.strip()
    ]
    reason_text = ""
    if reason_bits:
        clipped = "; ".join(reason_bits)[:500]
        reason_text = f" Gate reason: {clipped}."
    extra = ""
    if node_id == "plan":
        extra = (
            " PLAN.json done_when must be a JSON array of relative file paths, "
            "not a sentence."
        )
    searchish = any(
        "search" in item.lower() or "citation" in item.lower() for item in reason_bits
    )
    action = (
        "Call `parallel-search-*_web_search` again, then write the notes. "
        if searchish
        else "Write only the missing artifacts for this node, then stop. "
    )
    return (
        f"Node `{node_id}` is not done. Missing: {listed}.{reason_text} "
        f"{action}"
        "Do not start the next node. "
        "The user-visible reply is about their task, not these files."
        f"{extra}"
    )


def _missing_required(
    sandbox_id: UUID, session_id: UUID, node: GraphNode
) -> list[GateMissing]:
    return [
        GateMissing(
            path=path,
            reason="missing or empty",
            owner_node=node.id,
        )
        for path in node.required_paths
        if not _nonempty_path(sandbox_id, session_id, path)
    ]


def has_citation_marker(text: str) -> bool:
    return bool(_CITATION_RE.search(text or ""))


def _gate_lane(
    sandbox_id: UUID,
    session_id: UUID,
    node: GraphNode,
    *,
    search_required: bool = False,
) -> ContractGateResult:
    missing: list[GateMissing] = []
    if not node.required_paths:
        return ContractGateResult(
            passed=False,
            missing=[
                GateMissing(
                    path=node.id,
                    reason="missing or empty",
                    owner_node=node.id,
                )
            ],
        )
    for path in node.required_paths:
        text = _read_full_text(sandbox_id, session_id, path)
        if not text.strip():
            missing.append(
                GateMissing(path=path, reason="missing or empty", owner_node=node.id)
            )
        elif search_required and not has_citation_marker(text):
            missing.append(
                GateMissing(
                    path=path,
                    reason="search required but no verifiable citation",
                    owner_node=node.id,
                )
            )
    for path in _LANE_OUT_OF_BOUNDS:
        if path in node.required_paths:
            continue
        if path.endswith("/"):
            if _directory_has_files(sandbox_id, session_id, path):
                missing.append(
                    GateMissing(
                        path=path,
                        reason="lane wrote outside its directory",
                        owner_node=node.id,
                    )
                )
        elif _nonempty_path(sandbox_id, session_id, path):
            missing.append(
                GateMissing(
                    path=path,
                    reason="lane wrote outside its directory",
                    owner_node=node.id,
                )
            )
    if missing:
        return ContractGateResult(passed=False, missing=missing)
    return ContractGateResult(passed=True)


def _directory_has_files(sandbox_id: UUID, session_id: UUID, path: str) -> bool:
    try:
        entries = get_sandbox_manager().list_directory(sandbox_id, session_id, path)
    except Exception:
        return False
    return bool(entries)


def _gate_work(
    sandbox_id: UUID, session_id: UUID, node: GraphNode
) -> ContractGateResult:
    missing: list[GateMissing] = []
    done_required = DONE_JSON_PATH in node.required_paths
    done_present = _nonempty_path(sandbox_id, session_id, DONE_JSON_PATH)
    if done_required or done_present:
        try:
            raw = get_sandbox_manager().read_file(
                sandbox_id, session_id, DONE_JSON_PATH
            )
            _parse_done(raw)
        except Exception as exc:
            missing.append(
                GateMissing(
                    path=DONE_JSON_PATH,
                    reason=str(exc),
                    owner_node=node.id,
                )
            )
    if done_required:
        todo_text = _read_full_text(sandbox_id, session_id, TODO_MD_PATH)
        if todo_text and _OPEN_TODO_RE.search(todo_text):
            missing.append(
                GateMissing(
                    path=TODO_MD_PATH,
                    reason="TODO.md still has open items",
                    owner_node=node.id,
                )
            )
    if missing:
        return ContractGateResult(passed=False, missing=missing)
    return ContractGateResult(passed=True)


def _parse_done(raw: bytes) -> dict[str, Any]:
    import json

    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("DONE.json must be an object")
    if payload.get("done") is not True:
        raise ValueError("DONE.json needs done: true")
    return payload


def _read_full_text(sandbox_id: UUID, session_id: UUID, path: str) -> str:
    try:
        raw = get_sandbox_manager().read_file(sandbox_id, session_id, path)
    except Exception:
        return ""
    if not isinstance(raw, (bytes, bytearray)):
        return ""
    return raw.decode("utf-8", errors="replace")


def _gate_plan(
    sandbox_id: UUID, session_id: UUID, node: GraphNode
) -> ContractGateResult:
    try:
        raw = get_sandbox_manager().read_file(sandbox_id, session_id, PLAN_JSON_PATH)
        parse_plan_bytes(raw)
    except Exception as exc:
        return ContractGateResult(
            passed=False,
            missing=[
                GateMissing(
                    path="outputs/plan/PLAN.json",
                    reason=str(exc),
                    owner_node=node.id,
                )
            ],
        )
    return ContractGateResult(passed=True)


def _gate_review(
    sandbox_id: UUID, session_id: UUID, node: GraphNode
) -> ContractGateResult:
    try:
        raw = get_sandbox_manager().read_file(sandbox_id, session_id, REVIEW_JSON_PATH)
        payload = _parse_review(raw)
    except Exception as exc:
        return ContractGateResult(
            passed=False,
            missing=[
                GateMissing(
                    path=REVIEW_JSON_PATH,
                    reason=str(exc),
                    owner_node=node.id,
                )
            ],
        )
    missing = [
        GateMissing(
            path=str(item.get("path") or item.get("channel") or ""),
            reason=str(item.get("reason") or "gap"),
            owner_node=str(item.get("owner_node") or node.id),
        )
        for item in payload.get("missing") or []
        if isinstance(item, dict)
    ]
    conflicts = [str(item) for item in payload.get("conflicts") or []]
    coverage = payload.get("coverage")
    coverage_value = float(coverage) if isinstance(coverage, (int, float)) else None
    passed = bool(payload.get("passed")) and not missing and not conflicts
    return ContractGateResult(
        passed=passed,
        missing=missing,
        conflicts=conflicts,
        coverage=coverage_value,
        review=payload,
    )


def _parse_review(raw: bytes) -> dict[str, Any]:
    import json

    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("REVIEW.json must be an object")
    if "passed" not in payload:
        verdict = payload.get("verdict")
        if payload.get("done") is True or verdict is True:
            payload["passed"] = True
        elif isinstance(verdict, str) and verdict.strip().lower() in {
            "pass",
            "passed",
            "ok",
            "conditional_deliverable",
        }:
            payload["passed"] = True
        else:
            raise ValueError("REVIEW.json needs passed")
    return payload


def _nonempty_path(sandbox_id: UUID, session_id: UUID, path: str) -> bool:
    text = _read_text(sandbox_id, session_id, path)
    if text:
        return True
    return _path_exists(sandbox_id, session_id, path)
