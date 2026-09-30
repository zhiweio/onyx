"""Runtime factory: capability lookup + profile resolution.

The runtime instance itself is constructed by the SessionManager at
serve-client creation time (it needs the container's base_url + password).
The factory's job is to expose the capability profile so the executor can
compensate for missing features without isinstance checks.
"""

from __future__ import annotations

import os

from onyx.server.features.build.sandbox.agent_runtime.base import (
    AgentRuntimeProfile,
    RuntimeCapability,
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
