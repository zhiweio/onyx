"""Scan sandbox artifacts and fold them into the artifacts channel."""

from __future__ import annotations

import hashlib
from uuid import UUID

from onyx.server.features.build.jobs.channels import ArtifactRecord, JobState
from onyx.server.features.build.jobs.durability import TREE_ROOTS, list_tree_files
from onyx.server.features.build.jobs.graph import GraphNode
from onyx.server.features.build.sandbox.factory import get_sandbox_manager

WATCH_PATHS = (
    "outputs/plan/PLAN.json",
    "outputs/plan/PLAN.md",
    "outputs/plan/TODO.json",
    "outputs/PLAN.md",
    "outputs/TODO.md",
    "outputs/MEMORY.md",
    "outputs/DONE.json",
    "outputs/ingest/MANIFEST.json",
    "outputs/analysis/ANALYSIS.md",
    "outputs/markdown/report.md",
    "outputs/review/REVIEW.json",
    "outputs/reconcile/RECONCILE.json",
    "outputs/reconcile/BLACKBOARD.md",
)
_TREE_LIMIT = 40


def scan_artifacts(
    *,
    sandbox_id: UUID,
    session_id: UUID,
    producer_node: str,
) -> dict[str, ArtifactRecord]:
    found: dict[str, ArtifactRecord] = {}
    manager = get_sandbox_manager()
    for path in WATCH_PATHS:
        record = _record_for(manager, sandbox_id, session_id, path, producer_node)
        if record is not None:
            found[record.path] = record
    for path in list_tree_files(
        manager, sandbox_id, session_id, TREE_ROOTS, limit=_TREE_LIMIT
    ):
        record = _record_for(manager, sandbox_id, session_id, path, producer_node)
        if record is not None:
            found[record.path] = record
    return found


def merge_node_outputs(
    state: JobState, node: GraphNode, produced: dict[str, ArtifactRecord]
) -> dict[str, dict[str, str | bool | None | list[str]]]:
    writes: dict[str, dict[str, str | bool | None | list[str]]] = {}
    for path in node.required_paths:
        record = produced.get(path) or state.artifacts.get(path)
        if record is None:
            continue
        writes[path] = record.model_dump()
    for path, record in produced.items():
        if path.startswith("outputs/") or path.startswith("project/"):
            writes[path] = record.model_dump()
    return writes


def _record_for(
    manager: object,
    sandbox_id: UUID,
    session_id: UUID,
    path: str,
    producer_node: str,
) -> ArtifactRecord | None:
    raw = _read_bytes(manager, sandbox_id, session_id, path)
    if raw is None:
        return None
    digest = _safe_summary(raw)
    return ArtifactRecord(
        path=path,
        hash=hashlib.sha256(raw).hexdigest()[:16],
        producer_node=producer_node,
        summary=digest,
        nonempty=bool(raw.strip()),
    )


def _safe_summary(raw: bytes) -> str:
    sample = raw[:400]
    if b"\x00" in sample:
        return "(binary)"
    digest = sample.decode("utf-8", errors="replace").replace("\x00", "").strip()
    if len(digest) > 240:
        return digest[:237] + "..."
    return digest


def _read_bytes(
    manager: object, sandbox_id: UUID, session_id: UUID, path: str
) -> bytes | None:
    try:
        raw = manager.read_file(sandbox_id, session_id, path)  # type: ignore[attr-defined]
    except Exception:
        return None
    if not isinstance(raw, (bytes, bytearray)):
        return None
    if not raw.strip():
        return None
    return bytes(raw)
