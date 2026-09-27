"""PiRuntime: drives the pi-coding-agent library in-process (via pi-serve).

Referencing QM ``pi-harness.ts:1620-1970``: pi embeds as a library
(``createAgentSession``), the session event stream is the data plane, and
platform tools are injected via ``customTools``. In Onyx the pi runtime
runs as a thin ``pi-serve`` HTTP wrapper inside the sandbox pod (mirrors
opencode-serve's lifecycle), with the same event schema the executor
already understands.

Phase-1 scope: capability profile + operations that delegate to the
pi-serve endpoints. The actual ``createAgentSession`` protocol integration
is the H2 follow-up.
"""

from __future__ import annotations

from typing import Any

from onyx.server.features.build.sandbox.agent_runtime.base import (
    AgentRuntime,
    AgentRuntimeProfile,
    RuntimeCapability,
)
from onyx.server.features.build.sandbox.models import PromptAttachment

_CAPABILITIES = frozenset(
    {
        RuntimeCapability.STEER,
        RuntimeCapability.SUBAGENTS,
        RuntimeCapability.MCP,
    }
)


class PiRuntime(AgentRuntime):
    """Drives the pi-coding-agent library via pi-serve in the sandbox pod."""

    profile = AgentRuntimeProfile(
        runtime_id="pi",
        capabilities=_CAPABILITIES,
    )

    def ensure_session(
        self,
        opencode_session_id: str,
        directory: str,
        **kwargs: Any,
    ) -> Any:
        raise NotImplementedError("pi-serve protocol lands in H2")

    def send_message(
        self,
        opencode_session_id: str,
        *,
        directory: str,
        prompt: str,
        attachments: list[PromptAttachment] | None = None,
        **kwargs: Any,
    ) -> Any:
        raise NotImplementedError("pi-serve protocol lands in H2")

    def abort(self, opencode_session_id: str, *, directory: str) -> None:
        raise NotImplementedError("pi-serve protocol lands in H2")

    def compact(self, opencode_session_id: str, *, directory: str) -> Any:
        raise NotImplementedError("pi-serve protocol lands in H2")

    def health_check(self) -> bool:
        raise NotImplementedError("pi-serve protocol lands in H2")

    def dispose(self, *, directory: str) -> None:
        raise NotImplementedError("pi-serve protocol lands in H2")

    def session_exists(self, opencode_session_id: str, *, directory: str) -> bool:
        raise NotImplementedError("pi-serve protocol lands in H2")

    def list_messages(
        self, opencode_session_id: str, *, directory: str
    ) -> list[dict[str, Any]]:
        raise NotImplementedError("pi-serve protocol lands in H2")

    def get_message(
        self, opencode_session_id: str, message_id: str, *, directory: str
    ) -> dict[str, Any] | None:
        raise NotImplementedError("pi-serve protocol lands in H2")

    def export_state(
        self, opencode_session_id: str, *, directory: str
    ) -> dict[str, Any]:
        raise NotImplementedError("pi-serve protocol lands in H2")

    def import_state(self, state: dict[str, Any], *, directory: str) -> None:
        raise NotImplementedError("pi-serve protocol lands in H2")
