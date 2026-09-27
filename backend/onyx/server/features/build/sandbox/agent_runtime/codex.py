"""CodexRuntime: drives the codex app-server (JSON-RPC over stdio) in-pod.

Referencing QM ``codex-harness.ts:931-1029``: each turn starts a codex
thread with ``dynamicTools`` (Onyx platform tools bridged as function
specs), injects prior history via ``thread/inject_items``, and reads
notification events for agent messages / tool calls. The codex CLI handles
its own sandbox (workspace-write scoped to the session dir) and model
routing (OpenAI-focused).

Phase-1 scope: capability profile + operations that delegate to the
daemon's process-bridge endpoints. The JSON-RPC protocol bridge (spawning
``codex app-server``, routing requests/responses) is the H1 follow-up.
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
        RuntimeCapability.COMPACT,
        RuntimeCapability.MCP,
        RuntimeCapability.HISTORY_SNAPSHOT,
    }
)


class CodexRuntime(AgentRuntime):
    """Drives the codex app-server inside the sandbox pod."""

    profile = AgentRuntimeProfile(
        runtime_id="codex",
        capabilities=_CAPABILITIES,
    )

    def ensure_session(
        self,
        opencode_session_id: str,
        directory: str,
        **kwargs: Any,
    ) -> Any:
        """thread/start with cwd=directory, sandbox=workspace-write."""
        raise NotImplementedError("codex protocol bridge lands in H1")

    def send_message(
        self,
        opencode_session_id: str,
        *,
        directory: str,
        prompt: str,
        attachments: list[PromptAttachment] | None = None,
        **kwargs: Any,
    ) -> Any:
        raise NotImplementedError("codex protocol bridge lands in H1")

    def abort(self, opencode_session_id: str, *, directory: str) -> None:
        raise NotImplementedError("codex protocol bridge lands in H1")

    def compact(self, opencode_session_id: str, *, directory: str) -> Any:
        raise NotImplementedError("codex protocol bridge lands in H1")

    def health_check(self) -> bool:
        raise NotImplementedError("codex protocol bridge lands in H1")

    def dispose(self, *, directory: str) -> None:
        raise NotImplementedError("codex protocol bridge lands in H1")

    def session_exists(self, opencode_session_id: str, *, directory: str) -> bool:
        raise NotImplementedError("codex protocol bridge lands in H1")

    def list_messages(
        self, opencode_session_id: str, *, directory: str
    ) -> list[dict[str, Any]]:
        raise NotImplementedError("codex protocol bridge lands in H1")

    def get_message(
        self, opencode_session_id: str, message_id: str, *, directory: str
    ) -> dict[str, Any] | None:
        raise NotImplementedError("codex protocol bridge lands in H1")

    def export_state(
        self, opencode_session_id: str, *, directory: str
    ) -> dict[str, Any]:
        """Codex state = the thread id for ``thread/resume``."""
        raise NotImplementedError("codex protocol bridge lands in H1")

    def import_state(self, state: dict[str, Any], *, directory: str) -> None:
        raise NotImplementedError("codex protocol bridge lands in H1")
