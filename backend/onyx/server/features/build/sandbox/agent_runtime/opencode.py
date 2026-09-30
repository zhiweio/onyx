"""OpenCodeRuntime: the ``AgentRuntime`` adapter over ``OpencodeServeClient``.

The serve client already implements every operation the ABC needs; this
adapter adds the capability profile and the ABC surface so the executor can
be migrated onto ``AgentRuntime`` without touching transport details.
Runtime switching (HarnessRouter) composes adapters like this one.
"""

from __future__ import annotations

from typing import Any, Generator

from onyx.llm.models import ReasoningEffort
from onyx.server.features.build.sandbox.agent_runtime.base import (
    AgentRuntime,
    AgentRuntimeProfile,
    RuntimeCapability,
)
from onyx.server.features.build.sandbox.models import PromptAttachment
from onyx.server.features.build.sandbox.opencode.serve_client import (
    OpencodeServeClient,
    SandboxEvent,
)

OPENCODE_PROFILE = AgentRuntimeProfile(
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
            RuntimeCapability.BACKGROUND_PROCESSES,
        }
    ),
)


class OpenCodeRuntime(AgentRuntime):
    """Drives an opencode-serve instance through its HTTP API."""

    profile = OPENCODE_PROFILE

    def __init__(self, client: OpencodeServeClient) -> None:
        self._client = client

    @property
    def client(self) -> OpencodeServeClient:
        """The underlying transport. Executors migrate off this gradually."""
        return self._client

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
        del model, reasoning_effort, agent_provider, agent_model, attachments
        return self._client.ensure_session(
            opencode_session_id or None, directory=directory
        )

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
        provider: str | None = None
        model_id: str | None = None
        if model and "/" in model:
            provider, _, model_id = model.partition("/")
        elif model:
            model_id = model
        return self._client.send_message(
            opencode_session_id,
            prompt,
            directory=directory,
            model_provider=provider,
            model_id=model_id,
            attachments=attachments,
        )

    def abort(self, opencode_session_id: str, *, directory: str) -> None:
        self._client.abort(opencode_session_id, directory=directory)

    def compact(
        self, opencode_session_id: str, *, directory: str, **kwargs: Any
    ) -> Generator[SandboxEvent, None, None]:
        model_provider = kwargs.get("model_provider") or ""
        model_id = kwargs.get("model_id") or ""
        return self._client.compact(
            opencode_session_id,
            directory=directory,
            model_provider=model_provider,
            model_id=model_id,
        )

    def health_check(self) -> bool:
        return self._client.health_check()

    def dispose(self, *, directory: str) -> None:
        self._client.dispose_instance(directory=directory)

    def session_exists(self, opencode_session_id: str, *, directory: str) -> bool:
        return self._client.session_exists(opencode_session_id, directory=directory)

    def list_messages(
        self, opencode_session_id: str, *, directory: str
    ) -> list[dict[str, Any]]:
        return self._client.list_messages(opencode_session_id, directory=directory)

    def get_message(
        self, opencode_session_id: str, message_id: str, *, directory: str
    ) -> dict[str, Any] | None:
        return self._client.get_message(
            opencode_session_id, message_id, directory=directory
        )
