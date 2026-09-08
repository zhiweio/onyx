"""Disk files that survive OpenCode turns. The host injects them each loop."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from onyx.server.features.build.jobs.plan import (
    DONE_JSON_PATH,
    MEMORY_MD_PATH,
    PLAN_JSON_PATH,
    PLAN_MD_PATH,
    TODO_MD_PATH,
)
from onyx.server.features.build.sandbox.models import FilesystemEntry

DURABILITY_FILES: tuple[str, ...] = (
    PLAN_MD_PATH,
    TODO_MD_PATH,
    MEMORY_MD_PATH,
    PLAN_JSON_PATH,
    DONE_JSON_PATH,
)
CACHE_DIRS: tuple[str, ...] = ("outputs/mcp", "outputs/commands")
TREE_ROOTS: tuple[str, ...] = (
    "outputs/mcp",
    "outputs/commands",
    "outputs/extracted",
    "outputs/exceptions",
    "outputs/lanes",
    "outputs/research",
    "project",
)

_MAX_CACHE_PATHS = 24
_MAX_WALK_DEPTH = 2
_SKIP_DIR_NAMES = {".venv", "node_modules"}

# Templates for agents and tests. Session setup does not write these.
SEED_PLAN_MD = "# Plan\n"
SEED_TODO_MD = "# Todo\n"
SEED_MEMORY_MD = (
    "# Memory\n"
    "\n"
    "Record only facts that later turns need: assumptions, missing sources, "
    "and user corrections.\n"
    "Do not paste tool output, MCP bodies, or chat transcripts.\n"
)


@dataclass(frozen=True)
class DurabilitySnapshot:
    files: dict[str, str] = field(default_factory=dict)
    caches: list[str] = field(default_factory=list)

    def format_for_brief(self) -> list[str]:
        present = [
            path for path in DURABILITY_FILES if self.files.get(path, "").strip()
        ]
        if not present:
            return []
        return [
            "On disk: "
            + ", ".join(present)
            + ". Read them if needed. Do not discuss these files."
        ]


def load_durability_snapshot(
    *,
    sandbox_id: UUID | None,
    session_id: UUID | None,
    manager: Any | None = None,
) -> DurabilitySnapshot:
    if sandbox_id is None or session_id is None:
        return DurabilitySnapshot()
    try:
        if manager is None:
            from onyx.server.features.build.sandbox.factory import get_sandbox_manager

            manager = get_sandbox_manager()
        files = {
            path: _read_text(manager, sandbox_id, session_id, path)
            for path in DURABILITY_FILES
        }
        caches = list_tree_files(
            manager,
            sandbox_id,
            session_id,
            CACHE_DIRS,
            limit=_MAX_CACHE_PATHS,
        )
        return DurabilitySnapshot(files=files, caches=caches)
    except Exception:
        return DurabilitySnapshot()


def list_tree_files(
    manager: Any,
    sandbox_id: UUID,
    session_id: UUID,
    roots: tuple[str, ...] | list[str],
    *,
    limit: int = _MAX_CACHE_PATHS,
) -> list[str]:
    found: list[str] = []
    for root in roots:
        _walk(manager, sandbox_id, session_id, root, found, depth=0, limit=limit)
        if len(found) >= limit:
            break
    return found


def _walk(
    manager: Any,
    sandbox_id: UUID,
    session_id: UUID,
    path: str,
    found: list[str],
    *,
    depth: int,
    limit: int,
) -> None:
    if len(found) >= limit or depth > _MAX_WALK_DEPTH:
        return
    try:
        entries = manager.list_directory(sandbox_id, session_id, path)
    except Exception:
        return
    if not isinstance(entries, list):
        return
    for entry in entries:
        child, is_dir = _normalize_entry(entry, path)
        if not child or child in {".", ".."}:
            continue
        name = child.rsplit("/", 1)[-1]
        if name in _SKIP_DIR_NAMES:
            continue
        if is_dir:
            _walk(
                manager,
                sandbox_id,
                session_id,
                child,
                found,
                depth=depth + 1,
                limit=limit,
            )
            continue
        found.append(child)
        if len(found) >= limit:
            return


def _normalize_entry(entry: Any, parent: str) -> tuple[str, bool]:
    if isinstance(entry, str):
        name = entry.strip().replace("\\", "/").lstrip("/")
        if not name:
            return "", False
        if name.startswith("outputs/") or name.startswith("project/"):
            return name, False
        return f"{parent.rstrip('/')}/{name}", False
    if not isinstance(entry, FilesystemEntry):
        return "", False
    name = entry.name.strip()
    raw_path = entry.path.strip().replace("\\", "/")
    if raw_path.startswith("outputs/") or raw_path.startswith("project/"):
        return raw_path.lstrip("/"), entry.is_directory
    if name:
        return f"{parent.rstrip('/')}/{name}", entry.is_directory
    if raw_path:
        return f"{parent.rstrip('/')}/{raw_path.lstrip('/')}", entry.is_directory
    return "", False


def _read_text(manager: Any, sandbox_id: UUID, session_id: UUID, path: str) -> str:
    try:
        raw = manager.read_file(sandbox_id, session_id, path)
    except Exception:
        return ""
    if not isinstance(raw, (bytes, bytearray)):
        return ""
    return raw.decode("utf-8", errors="replace")
