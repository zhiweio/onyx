"""Scenario resource bindings: the declarative contract between a Scenario
and the execution layer.

A scenario binds, per phase and at scenario level:

- ``skills`` — which skills the phase may use
- ``mcp_server_ids`` — which external MCP servers the phase may call
  (platform tools are always present; these gate external servers)
- ``document_sets`` — the rag_search retrieval scope
- ``web_search`` — whether live web tools are allowed in this phase
- ``gate`` — the human gate before the phase's work ships

Scenario-level values are defaults; phase-level values override. The
``runtime`` policy pins a runtime/model and feeds the HarnessRouter's
scenario precedence level.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from onyx.server.features.build.jobs.plan import JobPlan, JobPlanPhase
from onyx.server.features.build.sandbox.agent_runtime.router import (
    RuntimeResolutionRequest,
)
from onyx.server.features.scenario.playbook import ScenarioPlaybook


class PhaseGate(str, Enum):
    """Human gate applied to a phase's output before it counts as done."""

    NONE = "none"
    APPROVE_PLAN = "approve_plan"  # human approves the phase plan
    APPROVE_DELIVERY = "approve_delivery"  # human approves the artifact


class PhaseResourceBinding(BaseModel):
    """Resources one phase may use. All lists are allowlists."""

    model_config = {"extra": "allow"}

    skills: list[str] = Field(default_factory=list)
    mcp_server_ids: list[int] = Field(default_factory=list)
    document_sets: list[str] = Field(default_factory=list)
    web_search: bool = True
    gate: PhaseGate = PhaseGate.NONE


class ScenarioRuntimePolicy(BaseModel):
    """Scenario-level defaults and runtime pinning."""

    model_config = {"extra": "allow"}

    bindings: PhaseResourceBinding = Field(default_factory=PhaseResourceBinding)
    runtime: str | None = None
    model: str | None = None
    delivery_actions: list[str] = Field(default_factory=list)


def _binding_from_raw(raw: dict[str, Any] | None) -> PhaseResourceBinding:
    if not raw:
        return PhaseResourceBinding()
    return PhaseResourceBinding.model_validate(raw)


def parse_scenario_policy(rules: dict[str, Any] | None) -> ScenarioRuntimePolicy:
    """Parse the ``runtime``/``bindings`` keys of a scenario's rules.

    Tolerant of absent or partial data: a scenario without bindings gets
    neutral defaults (everything the user could otherwise use).
    """
    playbook = ScenarioPlaybook.model_validate(rules or {})
    raw = playbook.runtime if isinstance(playbook.runtime, dict) else None
    if raw is None and rules:
        raw_runtime = rules.get("runtime")
        raw = raw_runtime if isinstance(raw_runtime, dict) else None
    if raw is None:
        return ScenarioRuntimePolicy()
    policy = ScenarioRuntimePolicy.model_validate(raw)
    if isinstance(raw.get("bindings"), dict):
        policy.bindings = PhaseResourceBinding.model_validate(raw["bindings"])
    return policy


def resolve_phase_bindings(
    rules: dict[str, Any] | None,
) -> dict[str, PhaseResourceBinding]:
    """Per-phase bindings after merging over scenario defaults.

    Lists replace (not concatenate) on override — an explicit phase
    allowlist is a statement of exactly what the phase may use.
    """
    policy = parse_scenario_policy(rules)
    defaults = policy.bindings
    playbook = ScenarioPlaybook.model_validate(rules or {})
    merged: dict[str, PhaseResourceBinding] = {}
    for phase in playbook.phases:
        raw = phase.bindings if isinstance(phase.bindings, dict) else None
        override = _binding_from_raw(raw)
        merged[phase.id] = PhaseResourceBinding(
            skills=override.skills if raw and override.skills else defaults.skills,
            mcp_server_ids=(
                override.mcp_server_ids
                if raw and override.mcp_server_ids
                else defaults.mcp_server_ids
            ),
            document_sets=(
                override.document_sets
                if raw and override.document_sets
                else defaults.document_sets
            ),
            web_search=override.web_search if raw else defaults.web_search,
            gate=override.gate if raw and raw.get("gate") else defaults.gate,
        )
    return merged


def scenario_runtime_request(
    rules: dict[str, Any] | None,
) -> RuntimeResolutionRequest:
    """HarnessRouter request carrying the scenario's runtime pin."""
    policy = parse_scenario_policy(rules)
    return RuntimeResolutionRequest(
        scenario_runtime=policy.runtime,
        scenario_model=policy.model,
    )


def compile_scenario_plan(
    rules: dict[str, Any] | None,
    *,
    goal: str,
) -> JobPlan:
    """Compile a scenario playbook into a host JobPlan.

    Playbook phases become planned phases (``done_when`` becomes the
    completion criteria); ``ask_delivery`` is on when any phase (or the
    scenario default) gates delivery for human approval.
    """
    playbook = ScenarioPlaybook.model_validate(rules or {})
    policy = parse_scenario_policy(rules)
    phases: list[JobPlanPhase] = []
    ask_delivery = policy.bindings.gate == PhaseGate.APPROVE_DELIVERY
    for phase in playbook.phases:
        if not phase.id:
            continue
        if phase.bindings and isinstance(phase.bindings, dict):
            gate_raw = phase.bindings.get("gate")
            if gate_raw == PhaseGate.APPROVE_DELIVERY.value:
                ask_delivery = True
        phases.append(
            JobPlanPhase(
                id=phase.id,
                kind="phase",
                done_when=[phase.done_when] if phase.done_when else [],
            )
        )
    return JobPlan(
        goal=goal,
        phases=phases,
        lanes=[],
        inputs=list(playbook.required_inputs),
        ask_delivery=ask_delivery,
        done_when=list(playbook.deliverables),
    )


def bindings_for_phase(
    rules: dict[str, Any] | None, phase_id: str
) -> PhaseResourceBinding:
    """Effective bindings for one phase id; scenario defaults when unknown."""
    return resolve_phase_bindings(rules).get(phase_id, PhaseResourceBinding())
