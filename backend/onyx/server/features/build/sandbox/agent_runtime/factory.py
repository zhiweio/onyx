"""Runtime factory: capability lookup, profile resolution, turn routing.

The runtime instance itself is constructed by the SessionManager at
serve-client creation time (it needs the container's base_url + password).
The factory exposes capability profiles (back-compat, env-selected) and
the per-turn ``resolve_runtime_for_turn`` entry point backed by the
``HarnessRouter`` precedence chain.
"""

from __future__ import annotations

import os

from onyx.server.features.build.sandbox.agent_runtime.base import (
    AgentRuntimeProfile,
    RuntimeCapability,
)
from onyx.server.features.build.sandbox.agent_runtime.router import (
    HarnessRouter,
    RuntimeChoice,
    RuntimeResolutionRequest,
    build_router_from_env,
)

_AGENT_RUNTIME_ENV = "SANDBOX_AGENT_RUNTIME"

# Capability profiles per runtime. OpenCode is the only one implemented;
# codex and pi are declared for the H1/H2 milestones.
_PROFILES: dict[str, AgentRuntimeProfile] = {
    "opencode": AgentRuntimeProfile(
        runtime_id="opencode",
        capabilities=frozenset(
            {
                RuntimeCapability.STEER,
                RuntimeCapability.COMPACT,
                RuntimeCapability.SUBAGENTS,
                RuntimeCapability.QUESTION_ASKS,
                RuntimeCapability.QUESTION_TIMEOUT_EVENTS,
                RuntimeCapability.TURN_BUDGET_STAMP,
                RuntimeCapability.MCP,
                RuntimeCapability.HISTORY_SNAPSHOT,
                RuntimeCapability.TURN_REWIND,
            }
        ),
    ),
    "codex": AgentRuntimeProfile(
        runtime_id="codex",
        capabilities=frozenset(
            {
                RuntimeCapability.STEER,
                RuntimeCapability.COMPACT,
                RuntimeCapability.MCP,
                RuntimeCapability.HISTORY_SNAPSHOT,
            }
        ),
    ),
    "pi": AgentRuntimeProfile(
        runtime_id="pi",
        capabilities=frozenset(
            {
                RuntimeCapability.STEER,
                RuntimeCapability.SUBAGENTS,
                RuntimeCapability.MCP,
            }
        ),
    ),
}


def get_runtime_profile() -> AgentRuntimeProfile:
    """Return the capability profile for the configured runtime."""
    runtime_id = os.environ.get(_AGENT_RUNTIME_ENV, "opencode").strip().lower()
    profile = _PROFILES.get(runtime_id)
    if profile is None:
        raise ValueError(
            f"Unknown SANDBOX_AGENT_RUNTIME {runtime_id!r}; "
            f"expected one of {sorted(_PROFILES)}"
        )
    return profile


def get_runtime_capabilities() -> frozenset[RuntimeCapability]:
    """Return just the capability set for the configured runtime."""
    return get_runtime_profile().capabilities


_router_singleton: HarnessRouter | None = None


def get_harness_router() -> HarnessRouter:
    """Deployment-level router (env-configured, process-cached)."""
    global _router_singleton
    if _router_singleton is None:
        _router_singleton = build_router_from_env()
    return _router_singleton


def resolve_runtime_for_turn(request: RuntimeResolutionRequest) -> RuntimeChoice:
    """Resolve ``(runtime, model)`` for one turn via the precedence chain."""
    return get_harness_router().resolve(request)
