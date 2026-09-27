"""Agent runtime port: the interface every sandbox agent runtime satisfies.

Referencing QM's ``HarnessAdapterProfile`` / Codex ``SessionTask``: the port
exists so a second runtime (pi, codex, a future CLI) can be added without
touching the executor. OpenCode is the only implementation today; the
factory exposes the capability profile by ``SANDBOX_AGENT_RUNTIME``.
"""

from onyx.server.features.build.sandbox.agent_runtime.base import (
    AgentRuntime,
    AgentRuntimeProfile,
    RuntimeCapability,
)
from onyx.server.features.build.sandbox.agent_runtime.factory import (
    get_runtime_profile,
)

__all__ = [
    "AgentRuntime",
    "AgentRuntimeProfile",
    "RuntimeCapability",
    "get_runtime_profile",
]
