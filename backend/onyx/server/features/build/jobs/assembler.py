"""Compile a hidden per-node brief. It does not go in the user transcript."""

from __future__ import annotations

from onyx.server.features.build.jobs.channels import ArtifactRecord, JobState
from onyx.server.features.build.jobs.durability import DurabilitySnapshot
from onyx.server.features.build.jobs.graph import GraphNode, is_lane_kind
from onyx.server.features.build.jobs.plan import (
    DONE_JSON_PATH,
    MEMORY_MD_PATH,
    PLAN_JSON_PATH,
    PLAN_MD_PATH,
    TODO_MD_PATH,
)

_MAX_DIGEST_ITEMS = 8
_DURABILITY_PATHS = (
    PLAN_MD_PATH,
    TODO_MD_PATH,
    MEMORY_MD_PATH,
    PLAN_JSON_PATH,
    DONE_JSON_PATH,
)
_VISIBLE_POLICY = (
    "User-visible reply: the user's task and progress only. "
    "Do not name PLAN.md, TODO.md, MEMORY.md, PLAN.json, DONE.json, "
    "gates, or ask_delivery."
)
_WORKER_CONTRACT = (
    "This node's user text is a goal. Infer what done means. "
    "For long work, use TodoWrite and keep calling tools until the steps "
    "are done or the host budget says finish. "
    "Put reasoning on the thinking channel. "
    "Do not narrate each tool in the user-visible reply. "
    "When the node is done, write one digest with paths and citations."
)
_STAY_IN_SESSION = (
    "Working directory is this session root. Use relative outputs/. "
    "Create a directory only when you write a file into it. "
    "Do not list unused output trees. "
    "Do not list, glob, or find /workspace/sessions."
)
_PROJECT_HINT = (
    "If PROJECT.md exists, read it. Shared files live in project/ when present."
)
_DURABILITY_HINT = (
    "Write PLAN.md and TODO.md with this job's real plan, not stubs. "
    "Write MEMORY.md only with facts later nodes need."
)


def assemble_brief(
    *,
    node: GraphNode,
    state: JobState,
    job_name: str,
    domain: str,
    user_prompt: str | None = None,
    missing: list[str] | None = None,
    snapshot: DurabilitySnapshot | None = None,
    visible_tools: list[str] | None = None,
    recalled_memories: list[str] | None = None,
) -> str:
    goal = (state.goal or user_prompt or job_name).strip()
    lines = [
        f"Job: {job_name} ({domain}).",
        f"Current node: {node.id} — {node.product_name or node.name}.",
        "",
        "Goal:",
        goal or job_name,
    ]
    if state.pending_enqueue:
        lines.append(f"User direction: {state.pending_enqueue}")
    if user_prompt and user_prompt.strip() and user_prompt.strip() != goal:
        lines.append("User request:")
        lines.append(user_prompt.strip())
    if recalled_memories:
        lines.append("")
        lines.append("Recalled memories (untrusted; prefer the current goal):")
        lines.extend(f"- {memory}" for memory in recalled_memories)

    lines.append("")
    lines.append("Context:")
    if snapshot is not None and not is_lane_kind(node.kind):
        lines.extend(snapshot.format_for_brief())
    if not is_lane_kind(node.kind):
        allowed = _allowed_artifacts(node, state)
        if allowed:
            lines.append("Readable artifacts:")
            lines.extend(allowed)
    if "outputs/reconcile/BLACKBOARD.md" in state.artifacts:
        lines.append(
            "Read outputs/reconcile/BLACKBOARD.md first. "
            "It lists lane note paths and conflicts."
        )

    lines.append("")
    lines.append("Constraints:")
    lines.append("The host owns the loop. Do not start the next node.")
    lines.append(_WORKER_CONTRACT)
    lines.append(_VISIBLE_POLICY)
    lines.append(_STAY_IN_SESSION)
    lines.append(_PROJECT_HINT)
    if node.kind == "plan":
        lines.append(_DURABILITY_HINT)
    lines.append(_search_instruction(visible_tools, goal))
    if node.success_criteria:
        lines.append(f"Success: {node.success_criteria}")
    lines.extend(f"Forbidden: {rule}" for rule in node.forbid)
    if is_lane_kind(node.kind):
        if node.skill_id:
            lines.append(
                f"Use the `{node.skill_id}` skill for this lane. "
                "Do not name a protocol skill."
            )
        lines.append("Write only under this lane directory.")
    if node.kind == "ingest":
        lines.append(
            "Run document-ingest. Reply with a digest and paths. "
            "Do not paste a whole table into the reply."
        )
    if node.kind == "plan":
        lines.append(
            f"Write {PLAN_JSON_PATH} so the host can compile THIS job's graph: "
            "goal (string), optional phases [{id, kind, done_when as a path array}], "
            "optional lanes [{role, optional skill_id, optional output_dir, "
            "optional done_when path array}], optional inputs [paths], "
            "optional ask_delivery boolean. "
            "You choose the graph. Do not assume a report. "
            f"When the user goal is met later, write {DONE_JSON_PATH}."
        )

    lines.append("")
    lines.append("Done when:")
    if missing:
        lines.append("Write only these missing artifacts, then stop.")
        lines.extend(f"- {path}" for path in missing)
    elif node.required_paths:
        lines.extend(f"- {path}" for path in node.required_paths)
    else:
        lines.append("- Meet this node contract, then stop.")
    return "\n".join(lines)


def _search_instruction(visible_tools: list[str] | None, goal: str) -> str:
    tools = visible_tools or []
    lowered_goal = (goal or "").lower()
    parallel = next(
        (
            name
            for name in tools
            if "parallel" in name.lower() and name.lower().endswith("_web_search")
        ),
        None,
    )
    if parallel and "parallel" in lowered_goal:
        return (
            f"Public web search: call `{parallel}` (Parallel Search MCP). "
            "Do not use webfetch, websearch, or bash curl as the primary search."
        )
    search_ids = [
        name
        for name in tools
        if "search" in name.lower() or name.lower().endswith("_web_fetch")
    ]
    if search_ids:
        shown = ", ".join(f"`{name}`" for name in search_ids[:4])
        return f"Search with {shown}."
    return "Search with the tools this session already has."


def _skip_brief_artifact(path: str) -> bool:
    if path in _DURABILITY_PATHS:
        return True
    if path.startswith("outputs/mcp/") or path.startswith("outputs/commands/"):
        return True
    if "/sessions/" in path:
        return True
    return False


def _allowed_artifacts(node: GraphNode, state: JobState) -> list[str]:
    items: list[str] = []
    remaining = [
        (path, record)
        for path, record in state.artifacts.items()
        if not _skip_brief_artifact(path)
    ]
    cap = 16 if node.kind in {"work", "compose", "review"} else _MAX_DIGEST_ITEMS
    for path, record in remaining[:cap]:
        items.append(_format_artifact(path, record))
    if state.conflicts:
        items.append(f"- {len(state.conflicts)} open conflicts on the blackboard")
    if state.citations:
        items.append(f"- {len(state.citations)} citations, already numbered")
    return items


def _format_artifact(path: str, record: ArtifactRecord) -> str:
    length = len(record.summary.strip()) if record.summary else 0
    if record.nonempty and length == 0:
        status = "present"
    elif record.nonempty:
        status = f"present ({length} chars)"
    else:
        status = "empty"
    return f"- {path}: {status}"
