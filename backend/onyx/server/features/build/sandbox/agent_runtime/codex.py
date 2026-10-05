"""CodexRuntime: drives the codex app-server (JSON-RPC over stdio) in-pod.

Transport runs through the sandbox daemon's codex bridge (see
``sandbox_daemon/codex_bridge.py`` + ``sandbox/codex/transport.py``).
Every turn is one ephemeral thread: history replays from the platform
tape (``thread/inject_items``), so the session's durable state never
lives inside codex — it lives with the platform, where it can be audited
and migrated across runtimes.

Capability notes (vs the opencode profile):
- COMPACT is host-side: a compact marks the tape and shrinks the replay
  budget; there is no native codex summarize call.
- QUESTION_ASKS / TURN_BUDGET_STAMP / TURN_REWIND / SUBAGENTS are absent;
  the executor degrades those flows via the profile (host hard budget
  still bounds every turn).
"""

from __future__ import annotations

from typing import Any

from onyx.db.engine.sql_engine import get_session_with_current_tenant
from onyx.llm.models import ReasoningEffort
from onyx.server.features.build.sandbox.agent_runtime.base import (
    AgentRuntime,
    AgentRuntimeProfile,
    RuntimeCapability,
)
from onyx.server.features.build.sandbox.codex.serve_client import CodexServeClient
from onyx.server.features.build.sandbox.models import PromptAttachment

_CAPABILITIES = frozenset(
    {
        RuntimeCapability.STEER,
        RuntimeCapability.COMPACT,
        RuntimeCapability.MCP,
        RuntimeCapability.HISTORY_SNAPSHOT,
    }
)

# Reasoning-effort map: Onyx's AUTO/MINIMAL/LOW/MEDIUM/HIGH → codex's
# low/medium/high/xhigh ladder.
_EFFORT_MAP = {
    "minimal": "low",
    "low": "low",
    "medium": "medium",
    "high": "high",
    "auto": None,  # let codex pick per model
}


class CodexRuntime(AgentRuntime):
    """Drives the codex app-server inside the sandbox pod."""

    profile = AgentRuntimeProfile(
        runtime_id="codex",
        capabilities=_CAPABILITIES,
    )

    def __init__(
        self,
        client: CodexServeClient,
        *,
        session_id: Any,
        base_instructions: str,
        reasoning_effort: ReasoningEffort = ReasoningEffort.AUTO,
    ) -> None:
        self._client = client
        self._session_id = session_id
        self._base_instructions = base_instructions
        self._reasoning_effort = reasoning_effort
        self._active_thread_id: str | None = None

    @property
    def client(self) -> CodexServeClient:
        return self._client

    # ── session bookkeeping ───────────────────────────────────────────
    # Threads are per-turn; the "session" is the platform tape.

    def ensure_session(
        self,
        opencode_session_id: str,
        directory: str,  # noqa: ARG002
        *,
        model: str | None = None,  # noqa: ARG002
        reasoning_effort: ReasoningEffort = ReasoningEffort.AUTO,
        agent_provider: str | None = None,  # noqa: ARG002
        agent_model: str | None = None,  # noqa: ARG002
        attachments: list[PromptAttachment] | None = None,  # noqa: ARG002
    ) -> Any:
        if reasoning_effort:
            self._reasoning_effort = reasoning_effort
        return opencode_session_id

    def session_exists(self, opencode_session_id: str, *, directory: str) -> bool:  # noqa: ARG002
        # The tape decides whether history exists, not codex.
        return True

    def dispose(self, *, directory: str) -> None:  # noqa: ARG002
        self._active_thread_id = None

    # ── turns ─────────────────────────────────────────────────────────

    def send_message(
        self,
        opencode_session_id: str,  # noqa: ARG002
        *,
        directory: str,
        prompt: str,
        attachments: list[PromptAttachment] | None = None,  # noqa: ARG002
        model: str | None = None,
        reasoning_effort: ReasoningEffort = ReasoningEffort.AUTO,
        timeout_s: float = 180.0,
        absolute_timeout_s: float | None = None,
        should_interrupt=None,
    ) -> Any:
        """Start the turn's thread and return the event stream generator."""
        from onyx.server.features.build.sandbox.codex.replay import (
            build_inject_items,
        )

        with get_session_with_current_tenant() as db_session:
            inject_items = build_inject_items(db_session, self._session_id)

        chosen_effort = (
            reasoning_effort or self._reasoning_effort or ReasoningEffort.AUTO
        )
        effort = _EFFORT_MAP.get(str(chosen_effort.value).lower())
        thread_id = self._client.start_thread(
            cwd=directory,
            base_instructions=self._base_instructions,
            model=model,
            reasoning_effort=effort,
            inject_items=inject_items or None,
        )
        self._active_thread_id = thread_id
        return self._client.stream_turn(
            thread_id=thread_id,
            prompt=prompt,
            attachments=None,
            timeout_s=timeout_s,
            absolute_timeout_s=absolute_timeout_s,
            should_interrupt=should_interrupt,
        )

    def abort(self, opencode_session_id: str, *, directory: str) -> None:  # noqa: ARG002
        if self._active_thread_id:
            self._client.interrupt(self._active_thread_id, None)

    def compact(self, opencode_session_id: str, *, directory: str) -> Any:  # noqa: ARG002
        """Host-side compact: mark the tape; the next replay shrinks."""
        from onyx.server.features.build.sandbox.tape_recorder import (
            record_context_event,
        )

        record_context_event("compaction", {"runtime": "codex", "summary": None})
        return {"ok": True}

    def health_check(self) -> bool:
        """True when the sandbox image carries the codex binary (never
        spawns the app-server just to answer a probe)."""
        try:
            status = self._client.transport.health(self._client.sandbox_id)
        except Exception:
            return False
        return bool(status.get("binary_available"))

    def list_messages(
        self,
        opencode_session_id: str,  # noqa: ARG002
        *,
        directory: str,  # noqa: ARG002
    ) -> list[dict[str, Any]]:
        """Serve the transcript from the tape (the durable truth)."""
        from onyx.server.features.build.sandbox.codex.replay import (
            build_inject_items,
        )

        with get_session_with_current_tenant() as db_session:
            return build_inject_items(db_session, self._session_id)  # type: ignore[return-value]

    def get_message(
        self,
        opencode_session_id: str,  # noqa: ARG002
        message_id: str,  # noqa: ARG002
        *,
        directory: str,  # noqa: ARG002
    ) -> dict[str, Any] | None:
        return None
