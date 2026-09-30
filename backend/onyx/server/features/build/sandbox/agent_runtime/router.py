"""Harness router: per-turn agent runtime resolution (QM harness-router.ts port).

Precedence chain, highest first:

1. ``purpose`` — what the turn is for (scenario run, scheduled fire,
   subagent, cheap classification). Purpose bindings are configured, not
   guessed.
2. explicit request — the user/session picked a runtime or model.
3. scenario configuration — the Scenario pinned a runtime for its runs.
4. org default — deployment-wide ``SANDBOX_AGENT_RUNTIME`` plus the
   registry default model.
5. safe fallback — the primary runtime and its default model.

Gating: the resolved runtime must be approved for the deployment. An
invalid *explicit* request raises ``NonRetryableRuntimeError`` (surface the
user's mistake); an invalid *derived* configuration falls back to the
runtime's default model and records why in the choice.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum

from onyx.server.features.build.sandbox.agent_runtime import models as model_registry
from onyx.utils.logger import setup_logger

logger = setup_logger()

AGENT_RUNTIME_ENV = "SANDBOX_AGENT_RUNTIME"
APPROVED_RUNTIMES_ENV = "SANDBOX_APPROVED_RUNTIMES"

PRIMARY_RUNTIME = "opencode"


class RuntimePurpose(str, Enum):
    """What a turn is for. Purposes may bind their own runtime+model."""

    CHAT = "chat"
    SCENARIO = "scenario"
    SCHEDULED = "scheduled"
    SUBAGENT = "subagent"
    CLASSIFY = "classify"  # cheap one-shots: titles, classifiers, judges


class NonRetryableRuntimeError(Exception):
    """The requested runtime/model combination can never run here."""


@dataclass(frozen=True)
class RuntimeChoice:
    runtime_id: str
    model_id: str
    origin: str  # which precedence level produced this choice
    note: str = ""


@dataclass(frozen=True)
class RuntimeResolutionRequest:
    """Inputs for one resolution. All fields optional; chain fills gaps."""

    purpose: RuntimePurpose | None = None
    requested_runtime: str | None = None
    requested_model: str | None = None
    scenario_runtime: str | None = None
    scenario_model: str | None = None


@dataclass(frozen=True)
class PurposeBinding:
    """A configured runtime+model for a purpose (e.g. cheap classify runs)."""

    runtime_id: str
    model_id: str | None = None


class HarnessRouter:
    """Resolves ``(runtime, model)`` per turn against the approved set."""

    def __init__(
        self,
        *,
        approved_runtimes: frozenset[str],
        org_default_runtime: str = PRIMARY_RUNTIME,
        purpose_bindings: dict[RuntimePurpose, PurposeBinding] | None = None,
    ) -> None:
        if org_default_runtime not in approved_runtimes:
            # The org default must itself be runnable; otherwise fall back
            # to the primary runtime and log loudly.
            logger.warning(
                "Org default runtime %r is not approved; using %r instead",
                org_default_runtime,
                PRIMARY_RUNTIME,
            )
            org_default_runtime = PRIMARY_RUNTIME
        self._approved = approved_runtimes
        self._org_default = org_default_runtime
        self._purpose_bindings = dict(purpose_bindings or {})

    @property
    def approved_runtimes(self) -> frozenset[str]:
        return self._approved

    # ── resolution ───────────────────────────────────────────────────────

    def resolve(self, request: RuntimeResolutionRequest) -> RuntimeChoice:
        """Apply the precedence chain; never returns an unapproved runtime."""
        choice = self._from_purpose(request)
        if choice is None:
            choice = self._from_explicit_request(request)
        if choice is None:
            choice = self._from_scenario(request)
        if choice is None:
            choice = self._org_default_choice()
        return self._finalize(choice)

    # ── precedence levels ────────────────────────────────────────────────

    def _from_purpose(
        self, request: RuntimeResolutionRequest
    ) -> RuntimeChoice | None:
        if request.purpose is None:
            return None
        binding = self._purpose_bindings.get(request.purpose)
        if binding is None:
            return None
        if binding.runtime_id not in self._approved:
            logger.warning(
                "Purpose %s binds unapproved runtime %s; ignoring binding",
                request.purpose.value,
                binding.runtime_id,
            )
            return None
        model_id = binding.model_id
        if model_id is None:
            model_id = model_registry.default_model_for(binding.runtime_id)
        if model_id is None or not model_registry.model_supported_by(
            model_id, binding.runtime_id
        ):
            model_id = model_registry.default_model_for(binding.runtime_id)
            assert model_id is not None  # approved runtime has a catalog model
        return RuntimeChoice(
            runtime_id=binding.runtime_id,
            model_id=model_id,
            origin=f"purpose:{request.purpose.value}",
        )

    def _from_explicit_request(
        self, request: RuntimeResolutionRequest
    ) -> RuntimeChoice | None:
        if request.requested_runtime is None and request.requested_model is None:
            return None

        runtime_id = request.requested_runtime
        if runtime_id is not None:
            if runtime_id not in self._approved:
                raise NonRetryableRuntimeError(
                    f"Runtime {runtime_id!r} is not approved for this deployment; "
                    f"approved: {sorted(self._approved)}"
                )
        else:
            # Model-only request: keep the org default runtime if it can
            # drive the model, otherwise pick the first approved one that can.
            model = request.requested_model
            assert model is not None
            runtime_id = self._runtime_for_model(model)
            if runtime_id is None:
                raise NonRetryableRuntimeError(
                    f"No approved runtime can drive model {model!r}"
                )

        model_id = request.requested_model
        if model_id is not None:
            if not model_registry.model_supported_by(model_id, runtime_id):
                raise NonRetryableRuntimeError(
                    f"Model {model_id!r} is not supported by runtime {runtime_id!r}"
                )
        else:
            model_id = model_registry.default_model_for(runtime_id)
            assert model_id is not None
        return RuntimeChoice(
            runtime_id=runtime_id, model_id=model_id, origin="request"
        )

    def _from_scenario(self, request: RuntimeResolutionRequest) -> RuntimeChoice | None:
        runtime_id = request.scenario_runtime
        if runtime_id is None:
            return None
        if runtime_id not in self._approved:
            logger.warning(
                "Scenario pins unapproved runtime %s; using org default", runtime_id
            )
            return None
        model_id = request.scenario_model
        if model_id is None or not model_registry.model_supported_by(
            model_id, runtime_id
        ):
            fallback = model_registry.default_model_for(runtime_id)
            note = "" if model_id is None else f"model {model_id!r} unsupported here"
            model_id = fallback
            assert model_id is not None
        else:
            note = ""
        return RuntimeChoice(
            runtime_id=runtime_id, model_id=model_id, origin="scenario", note=note
        )

    def _org_default_choice(self) -> RuntimeChoice:
        runtime_id = self._org_default
        model_id = model_registry.default_model_for(runtime_id)
        assert model_id is not None
        return RuntimeChoice(runtime_id=runtime_id, model_id=model_id, origin="org_default")

    # ── helpers ──────────────────────────────────────────────────────────

    def _runtime_for_model(self, model_id: str) -> str | None:
        for runtime in sorted(self._approved):
            if model_registry.model_supported_by(model_id, runtime):
                return runtime
        return None

    def _finalize(self, choice: RuntimeChoice) -> RuntimeChoice:
        """Guarantee the invariants the executor relies on."""
        if choice.runtime_id not in self._approved:
            # Derived choices were already screened; this guards config drift.
            fallback = self._org_default_choice()
            logger.warning(
                "Resolved runtime %s not approved; falling back to %s",
                choice.runtime_id,
                fallback.runtime_id,
            )
            return fallback
        if not model_registry.model_supported_by(choice.model_id, choice.runtime_id):
            model_id = model_registry.default_model_for(choice.runtime_id)
            assert model_id is not None
            return RuntimeChoice(
                runtime_id=choice.runtime_id,
                model_id=model_id,
                origin=choice.origin,
                note=f"model {choice.model_id!r} fell back to default",
            )
        return choice


def default_purpose_bindings() -> dict[RuntimePurpose, PurposeBinding]:
    """Standard purpose bindings: cheap models for classification work."""
    return {
        RuntimePurpose.CLASSIFY: PurposeBinding(
            runtime_id=PRIMARY_RUNTIME, model_id="glm-4.5-air"
        ),
        RuntimePurpose.SUBAGENT: PurposeBinding(
            runtime_id=PRIMARY_RUNTIME, model_id="glm-4.5-air"
        ),
    }


def build_router_from_env() -> HarnessRouter:
    """Deployment-level router from environment configuration."""
    approved_raw = os.environ.get(APPROVED_RUNTIMES_ENV, "").strip()
    if approved_raw:
        approved = frozenset(
            item.strip().lower() for item in approved_raw.split(",") if item.strip()
        )
    else:
        approved = frozenset({PRIMARY_RUNTIME})
    if PRIMARY_RUNTIME not in approved:
        approved = approved | {PRIMARY_RUNTIME}
    org_default = (
        os.environ.get(AGENT_RUNTIME_ENV, PRIMARY_RUNTIME).strip().lower() or PRIMARY_RUNTIME
    )
    return HarnessRouter(
        approved_runtimes=approved,
        org_default_runtime=org_default,
        purpose_bindings=default_purpose_bindings(),
    )
