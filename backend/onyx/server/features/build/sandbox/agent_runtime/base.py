"""Agent runtime contract: the operations the executor drives per turn.

Referencing QM ``harness.ts:219-248`` (profile/capabilities/router) and
Codex ``SessionTask``: each runtime declares a capability profile and
implements the operations the executor needs. Missing capabilities are
handled by executor-side compensation (skipping ask chips, skipping
compact turns, relying on host-side hard budget caps), not by requiring
every runtime to implement everything.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any

from onyx.llm.models import ReasoningEffort
from onyx.server.features.build.sandbox.models import PromptAttachment


class RuntimeCapability(Enum):
    """Feature flags a runtime may or may not support. The executor checks
    these to skip unsupported flows instead of failing at the call site."""

    STEER = "steer"
    COMPACT = "compact"
    SUBAGENTS = "subagents"
    QUESTION_ASKS = "question_asks"
    QUESTION_TIMEOUT_EVENTS = "question_timeout_events"
    TURN_BUDGET_STAMP = "turn_budget_stamp"
    MCP = "mcp"
    HISTORY_SNAPSHOT = "history_snapshot"
    BACKGROUND_PROCESSES = "background_processes"


class AgentRuntimeProfile:
    """Declarative capability set + identity for one runtime.

    Each concrete runtime exposes one of these as a class attribute so the
    executor (and future routing code) can branch without isinstance checks.
    """

    runtime_id: str
    capabilities: frozenset[RuntimeCapability]

    def __init__(
        self, runtime_id: str, capabilities: frozenset[RuntimeCapability]
    ) -> None:
        self.runtime_id = runtime_id
        self.capabilities = capabilities

    def has(self, cap: RuntimeCapability) -> bool:
        return cap in self.capabilities


class AgentRuntime(ABC):
    """The operations the executor drives per turn against a sandbox agent.

    This is the port every runtime satisfies. The executor depends on this
    ABC (via the SessionManager's composition), never on a concrete class.
    """

    profile: AgentRuntimeProfile

    @abstractmethod
    def ensure_session(
        self,
        opencode_session_id: str,
        directory: str,
        *,
        model: str | None = None,
        reasoning_effort: ReasoningEffort = ReasoningEffort.AUTO,
        agent_provider: str | None = None,
        agent_model: str | None = None,
        attachments: list[PromptAttachment] | None = None,
    ) -> Any:
        """Create or reattach a session for the given directory."""

    @abstractmethod
    def send_message(
        self,
        opencode_session_id: str,
        *,
        directory: str,
        prompt: str,
        attachments: list[PromptAttachment] | None = None,
        model: str | None = None,
        reasoning_effort: ReasoningEffort = ReasoningEffort.AUTO,
    ) -> Any:
        """Send a user turn to the agent and stream events."""

    @abstractmethod
    def abort(self, opencode_session_id: str, *, directory: str) -> None:
        """Abort the in-flight turn."""

    @abstractmethod
    def compact(self, opencode_session_id: str, *, directory: str) -> Any:
        """Trigger context compaction."""

    @abstractmethod
    def health_check(self) -> bool:
        """Whether the runtime is reachable."""

    @abstractmethod
    def dispose(self, *, directory: str) -> None:
        """Dispose the runtime instance for a directory."""

    @abstractmethod
    def session_exists(self, opencode_session_id: str, *, directory: str) -> bool:
        """Whether the runtime still knows about this session."""

    @abstractmethod
    def list_messages(
        self, opencode_session_id: str, *, directory: str
    ) -> list[dict[str, Any]]:
        """List all messages in the session."""

    @abstractmethod
    def get_message(
        self, opencode_session_id: str, message_id: str, *, directory: str
    ) -> dict[str, Any] | None:
        """Fetch a single message."""
