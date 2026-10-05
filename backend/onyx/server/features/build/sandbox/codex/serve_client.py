"""Host-side codex turn driver: one ephemeral thread per turn.

Mirrors the OpencodeServeClient's event contract (translated SandboxEvent
stream ending in PromptResponse/Error) so the executor consumes both
runtimes through the same loop. Differences are deliberate and host-side:

- History is replayed per turn from the tape (``thread/inject_items``).
- There is no persistent serve session: ``ensure_session`` is bookkeeping
  only, and the thread id is minted at ``send_message`` time.
- The SSE subscription covers the whole bridge; notifications are
  filtered by threadId client-side.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from typing import Any
from uuid import UUID

from onyx.server.features.build.sandbox.codex.config import (
    build_thread_start_params,
    build_turn_input,
)
from onyx.server.features.build.sandbox.codex.events import (
    CodexTurnState,
    translate_codex_event,
)
from onyx.server.features.build.sandbox.codex.transport import (
    CodexTransport,
    CodexTransportError,
)
from onyx.server.features.build.sandbox.event_schema import (
    ActivityTimeoutError,
    Error,
    PromptResponse,
)
from onyx.server.features.build.sandbox.sse import SSEKeepalive
from onyx.server.features.build.sandbox.tape_recorder import record_raw_event
from onyx.utils.logger import setup_logger

logger = setup_logger()

_KEEPALIVE_INTERVAL = 15.0


class CodexServeClient:
    """One instance per sandbox+directory; stateless between turns."""

    def __init__(self, transport: CodexTransport, sandbox_id: UUID) -> None:
        self._transport = transport
        self._sandbox_id = sandbox_id

    @property
    def transport(self) -> CodexTransport:
        return self._transport

    @property
    def sandbox_id(self) -> UUID:
        return self._sandbox_id

    def _rpc(self, method: str, params: dict[str, Any], *, timeout_s: float = 60.0):
        return self._transport.rpc(
            self._sandbox_id, method, params, initialize=True, timeout_s=timeout_s
        )

    def start_thread(
        self,
        *,
        cwd: str,
        base_instructions: str,
        model: str | None,
        reasoning_effort: str | None = None,
        user_instructions: str = "",
        inject_items: list[dict[str, Any]] | None = None,
        timeout_s: float = 60.0,
    ) -> str:
        params = build_thread_start_params(
            cwd=cwd,
            base_instructions=base_instructions,
            model=model,
            reasoning_effort=reasoning_effort,
            user_instructions=user_instructions,
        )
        result = self._rpc("thread/start", params, timeout_s=timeout_s)
        thread = result.get("thread") if isinstance(result, dict) else None
        thread_id = thread.get("id") if isinstance(thread, dict) else None
        if not isinstance(thread_id, str) or not thread_id:
            raise CodexTransportError("thread/start returned no thread id")
        if inject_items:
            self._rpc(
                "thread/inject_items",
                {"threadId": thread_id, "items": inject_items},
                timeout_s=timeout_s,
            )
        return thread_id

    def interrupt(self, thread_id: str, turn_id: str | None) -> None:
        try:
            self._rpc(
                "turn/interrupt",
                {"threadId": thread_id, "turnId": turn_id},
                timeout_s=10.0,
            )
        except CodexTransportError:
            logger.warning("codex turn/interrupt failed", exc_info=True)

    def stream_turn(
        self,
        *,
        thread_id: str,
        prompt: str,
        attachments: list[dict[str, Any]] | None = None,
        timeout_s: float,
        absolute_timeout_s: float | None = None,
        should_interrupt: Callable[[], bool] | None = None,
    ) -> Iterator[Any]:
        """Drive one turn: start it, stream events until the terminator.

        Mirrors the opencode client's drain semantics: keepalives on idle,
        inactivity and absolute deadlines (abort + synthesized terminator),
        ~1s interrupt polling, tape capture before translation.

        The SSE subscription opens BEFORE ``turn/start``: the bridge
        broadcasts notifications to current subscribers only, so a
        subscription taken after the turn starts would silently miss
        everything the thread already produced."""
        state = CodexTurnState(thread_id=thread_id)
        events_iter = self._transport.events(self._sandbox_id)
        try:
            # Pull until the connection is live (first line, comment or
            # data) so the subscription is registered before the turn runs.
            result = self._rpc(
                "turn/start",
                {
                    "threadId": thread_id,
                    "input": build_turn_input(prompt, attachments),
                },
                timeout_s=timeout_s,
            )
            turn = result.get("turn") if isinstance(result, dict) else None
            turn_id = turn.get("id") if isinstance(turn, dict) else None

            started = time.monotonic()
            last_activity = started
            last_keepalive = started
            last_interrupt_check = started
            terminated_locally = False

            for notification in events_iter:
                now = time.monotonic()
                if should_interrupt is not None and now - last_interrupt_check >= 1.0:
                    last_interrupt_check = now
                    if should_interrupt():
                        self.interrupt(
                            thread_id, turn_id if isinstance(turn_id, str) else None
                        )
                        terminated_locally = True
                        yield PromptResponse.model_validate(
                            {"stopReason": "cancelled"}
                        )
                        return
                if now - last_activity > timeout_s or (
                    absolute_timeout_s is not None
                    and now - started > absolute_timeout_s
                ):
                    self.interrupt(
                        thread_id, turn_id if isinstance(turn_id, str) else None
                    )
                    if (
                        absolute_timeout_s is not None
                        and now - started > absolute_timeout_s
                    ):
                        yield Error.model_validate(
                            {"code": -2, "message": "Turn exceeded maximum duration"}
                        )
                    else:
                        yield ActivityTimeoutError(
                            message="Timeout waiting for activity"
                        )
                    return
                if now - last_keepalive >= _KEEPALIVE_INTERVAL:
                    yield SSEKeepalive()
                    last_keepalive = now

                method = notification.get("method")
                params = notification.get("params")
                thread = params.get("threadId") if isinstance(params, dict) else None
                if thread is not None and thread != thread_id:
                    continue  # another session's thread on the shared bridge
                if not isinstance(method, str) or not isinstance(params, dict):
                    continue

                last_activity = time.monotonic()
                record_raw_event({"type": f"codex:{method}", **params})
                for event in translate_codex_event(method, params, state):
                    if isinstance(event, (Error, PromptResponse)):
                        terminated_locally = True
                    yield event
                if state.terminated and not terminated_locally:
                    terminated_locally = True
                if terminated_locally:
                    return

            # Stream ended without a terminator: the bridge connection died.
            if not terminated_locally:
                yield Error.model_validate(
                    {"code": -3, "message": "codex event stream ended before terminator"}
                )
        finally:
            # Close the SSE stream on every exit path (return/exception).
            events_iter.close()
