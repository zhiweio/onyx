"""Agent runtime port: the interface every sandbox agent runtime satisfies.

Referencing QM's ``HarnessAdapterProfile`` / ``harness-router.ts``: the port
exists so a second runtime (pi, codex, a future CLI) can be added without
touching the executor. OpenCode is the implemented runtime; the
``HarnessRouter`` resolves runtime+model per turn through the precedence
chain (purpose > request > scenario > org default > fallback).
"""

from onyx.server.features.build.sandbox.agent_runtime.base import (
    AgentRuntime,
    AgentRuntimeProfile,
    RuntimeCapability,
)
from onyx.server.features.build.sandbox.agent_runtime.factory import (
    get_runtime_capabilities,
    get_runtime_profile,
    resolve_runtime_for_turn,
)
from onyx.server.features.build.sandbox.agent_runtime.models import (
    AgentModelSpec,
    fingerprint,
    get_model_spec,
    iter_models,
    model_supported_by,
)
from onyx.server.features.build.sandbox.agent_runtime.opencode import (
    OPENCODE_PROFILE,
    OpenCodeRuntime,
)
from onyx.server.features.build.sandbox.agent_runtime.router import (
    HarnessRouter,
    NonRetryableRuntimeError,
    PurposeBinding,
    RuntimeChoice,
    RuntimePurpose,
    RuntimeResolutionRequest,
)

__all__ = [
    "AgentRuntime",
    "AgentModelSpec",
    "AgentRuntimeProfile",
    "HarnessRouter",
    "NonRetryableRuntimeError",
    "OPENCODE_PROFILE",
    "OpenCodeRuntime",
    "PurposeBinding",
    "RuntimeCapability",
    "RuntimeChoice",
    "RuntimePurpose",
    "RuntimeResolutionRequest",
    "fingerprint",
    "get_model_spec",
    "get_runtime_profile",
    "get_runtime_capabilities",
    "iter_models",
    "model_supported_by",
    "resolve_runtime_for_turn",
]
