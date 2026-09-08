"""Host-side stop and dump rules. Enforcement is here, not in a user skill."""

from __future__ import annotations

from uuid import UUID

from onyx.server.features.build.jobs.blackboard import scan_artifacts
from onyx.server.features.build.jobs.channels import ArtifactRecord
from onyx.server.features.build.jobs.gates import ContractGateResult, evaluate_contract_gate
from onyx.server.features.build.jobs.graph import GraphNode

LARGE_OUTPUT_HINT = (
    "If an MCP or table result is large, write it under outputs/mcp/ or "
    "outputs/extracted/ and keep only a digest in the reply."
)


def stop_gate(
    *,
    sandbox_id: UUID,
    session_id: UUID,
    node: GraphNode,
    deadline_exceeded: bool,
    attempts: int,
    search_required: bool = False,
) -> ContractGateResult:
    """Stop hook: the node is done only when the contract gate passes."""
    return evaluate_contract_gate(
        sandbox_id=sandbox_id,
        session_id=session_id,
        node=node,
        deadline_exceeded=deadline_exceeded,
        attempts=attempts,
        search_required=search_required,
    )


def collect_dumped_artifacts(
    *,
    sandbox_id: UUID,
    session_id: UUID,
    producer_node: str,
) -> dict[str, ArtifactRecord]:
    """PostToolUse equivalent: register bodies that landed on disk."""
    return scan_artifacts(
        sandbox_id=sandbox_id,
        session_id=session_id,
        producer_node=producer_node,
    )
