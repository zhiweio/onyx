"""Host-pure node workers. These do not call the model."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from onyx.server.features.build.jobs.graph import GraphNode
from onyx.server.features.build.jobs.reconcile import (
    reconcile_lanes,
    write_blackboard_file,
    write_reconcile_file,
)
from onyx.server.features.build.sandbox.factory import get_sandbox_manager

MANIFEST_PATH = "outputs/ingest/MANIFEST.json"
SOURCE_ROOTS = ("project", "user_library", "attachments")


@dataclass(frozen=True)
class HostWorkerResult:
    ok: bool
    fallback_to_worker: bool = False
    payload: dict[str, Any] | None = None
    error: str | None = None


def run_host_node(
    *,
    node: GraphNode,
    sandbox_id: UUID,
    session_id: UUID,
    state: Any,
    lane_nodes: list[GraphNode],
) -> HostWorkerResult:
    if node.kind == "ingest":
        return run_ingest(sandbox_id=sandbox_id, session_id=session_id)
    if node.kind == "reconcile":
        return run_reconcile(
            sandbox_id=sandbox_id,
            session_id=session_id,
            state=state,
            lane_nodes=lane_nodes,
        )
    return HostWorkerResult(ok=False, error=f"unknown host node {node.kind}")


def run_ingest(*, sandbox_id: UUID, session_id: UUID) -> HostWorkerResult:
    manager = get_sandbox_manager()
    if _exists(manager, sandbox_id, session_id, MANIFEST_PATH):
        return HostWorkerResult(ok=True, payload={"already": True})
    command = [
        "python",
        ".opencode/skills/document-ingest/scripts/ingest.py",
        "--roots",
        *SOURCE_ROOTS,
        "--out",
        "outputs",
    ]
    ran = _try_workspace_command(manager, sandbox_id, session_id, command)
    if ran and _exists(manager, sandbox_id, session_id, MANIFEST_PATH):
        return HostWorkerResult(ok=True, payload={"ran": True})
    indexed = _write_source_index(manager, sandbox_id, session_id)
    if indexed:
        return HostWorkerResult(ok=True, payload={"index": True})
    return HostWorkerResult(ok=False, fallback_to_worker=True)


def run_reconcile(
    *,
    sandbox_id: UUID,
    session_id: UUID,
    state: Any,
    lane_nodes: list[GraphNode],
) -> HostWorkerResult:
    payload, citations, conflicts = reconcile_lanes(
        sandbox_id=sandbox_id,
        session_id=session_id,
        state=state,
        lane_nodes=lane_nodes,
    )
    write_reconcile_file(
        sandbox_id=sandbox_id, session_id=session_id, payload=payload
    )
    write_blackboard_file(
        sandbox_id=sandbox_id, session_id=session_id, payload=payload
    )
    return HostWorkerResult(
        ok=True,
        payload={
            "reconcile": payload,
            "citations": {key: item.model_dump() for key, item in citations.items()},
            "conflicts": [item.model_dump() for item in conflicts],
        },
    )


def _try_workspace_command(
    manager: object,
    sandbox_id: UUID,
    session_id: UUID,
    command: list[str],
) -> bool:
    try:
        runner = manager.run_workspace_command  # type: ignore[attr-defined]
    except AttributeError:
        return False
    try:
        runner(sandbox_id, session_id, command)
        return True
    except Exception:
        return False


def _write_source_index(
    manager: object, sandbox_id: UUID, session_id: UUID
) -> bool:
    files: list[dict[str, str]] = []
    for root in SOURCE_ROOTS:
        names = _list(manager, sandbox_id, session_id, root)
        for name in names:
            files.append({"path": f"{root}/{name}", "status": "indexed"})
    payload = {"files": files, "source": "host_index"}
    raw = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    try:
        manager.write_files_to_sandbox(  # type: ignore[attr-defined]
            sandbox_id=sandbox_id,
            mount_path=f"/workspace/sessions/{session_id}",
            files={MANIFEST_PATH: raw},
        )
        return True
    except Exception:
        return False


def _exists(manager: object, sandbox_id: UUID, session_id: UUID, path: str) -> bool:
    try:
        raw = manager.read_file(sandbox_id, session_id, path)  # type: ignore[attr-defined]
    except Exception:
        return False
    return bool(raw)


def _list(
    manager: object, sandbox_id: UUID, session_id: UUID, path: str
) -> list[str]:
    try:
        names = manager.list_directory(sandbox_id, session_id, path)  # type: ignore[attr-defined]
    except Exception:
        return []
    if not isinstance(names, list):
        return []
    return [str(name) for name in names]
