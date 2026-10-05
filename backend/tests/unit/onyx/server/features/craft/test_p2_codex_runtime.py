"""P2 codex runtime: protocol translation, replay, config, router wiring."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from uuid import uuid4

from onyx.server.features.build.sandbox.codex.config import (
    build_codex_config_toml,
    build_codex_env_file,
    build_thread_start_params,
    build_turn_input,
)
from onyx.server.features.build.sandbox.codex.events import (
    CodexTurnState,
    translate_codex_event,
)
from onyx.server.features.build.sandbox.codex.replay import (
    build_inject_items,
    tape_item_to_inject,
)
from onyx.server.features.build.sandbox.event_schema import (
    AgentMessageChunk,
    AgentThoughtChunk,
    Error,
    PromptResponse,
)


def _state() -> CodexTurnState:
    return CodexTurnState(thread_id="thr_1")


def _events(method: str, params: dict[str, Any], state: CodexTurnState) -> list[Any]:
    return list(translate_codex_event(method, params, state))


def test_delta_translates_to_message_chunk() -> None:
    state = _state()
    events = _events(
        "item/agentMessage/delta",
        {"threadId": "thr_1", "itemId": "i1", "delta": "你好"},
        state,
    )
    assert len(events) == 1
    chunk = events[0]
    assert isinstance(chunk, AgentMessageChunk)
    assert chunk.content.text == "你好"


def test_reasoning_summary_translates_to_thought() -> None:
    state = _state()
    events = _events(
        "item/completed",
        {
            "threadId": "thr_1",
            "item": {
                "id": "r1",
                "type": "reasoning",
                "summary": ["step one", "step two"],
            },
        },
        state,
    )
    texts = [e.content.text for e in events]
    assert texts == ["step one", "step two"]
    assert all(isinstance(e, AgentThoughtChunk) for e in events)


def test_commentary_completed_without_delta_emits_once() -> None:
    state = _state()
    events = _events(
        "item/completed",
        {
            "threadId": "thr_1",
            "item": {
                "id": "c1",
                "type": "agentMessage",
                "phase": "commentary",
                "text": "note",
            },
        },
        state,
    )
    assert len(events) == 1
    assert events[0].content.text == "note"


def test_final_agent_message_completed_not_duplicated() -> None:
    state = _state()
    _events(
        "item/agentMessage/delta",
        {"threadId": "thr_1", "itemId": "m1", "delta": "hi"},
        state,
    )
    # completed final message after deltas must not re-emit the text
    events = _events(
        "item/completed",
        {
            "threadId": "thr_1",
            "item": {
                "id": "m1",
                "type": "agentMessage",
                "phase": "final_answer",
                "text": "hi",
            },
        },
        state,
    )
    assert events == []


def test_token_usage_dedup_and_granular_fields() -> None:
    state = _state()
    first = _events(
        "thread/tokenUsage/updated",
        {
            "threadId": "thr_1",
            "tokenUsage": {
                "total": {"inputTokens": 100, "outputTokens": 20},
                "last": {"inputTokens": 100},
            },
        },
        state,
    )
    assert len(first) == 1
    assert first[0].input_tokens == 100
    assert first[0].output_tokens == 20

    # Replayed identical totals are dropped.
    again = _events(
        "thread/tokenUsage/updated",
        {
            "threadId": "thr_1",
            "tokenUsage": {
                "total": {"inputTokens": 100, "outputTokens": 20},
                "last": {"inputTokens": 0},
            },
        },
        state,
    )
    assert again == []

    # Growth passes; last=0 falls back to the total delta.
    grown = _events(
        "thread/tokenUsage/updated",
        {
            "threadId": "thr_1",
            "tokenUsage": {
                "total": {"inputTokens": 150, "outputTokens": 50},
                "last": {"input_tokens": 0},
            },
        },
        state,
    )
    assert len(grown) == 1
    assert grown[0].input_tokens == 50
    assert grown[0].output_tokens == 30


def test_turn_completed_maps_stop_reasons() -> None:
    state = _state()
    events = _events(
        "turn/completed",
        {"threadId": "thr_1", "turn": {"id": "t1", "status": "completed"}},
        state,
    )
    assert isinstance(events[-1], PromptResponse)
    assert events[-1].stop_reason == "end_turn"

    state2 = _state()
    failed = _events(
        "turn/completed",
        {
            "threadId": "thr_1",
            "turn": {"id": "t1", "status": "failed", "error": {"message": "boom"}},
        },
        state2,
    )
    assert isinstance(failed[-1], Error)
    assert "boom" in failed[-1].message


def test_codex_exit_maps_to_transport_error() -> None:
    state = _state()
    events = _events("codex/exit", {}, state)
    assert isinstance(events[-1], Error)
    assert events[-1].code == -3
    assert state.terminated


def test_unknown_notification_ignored() -> None:
    state = _state()
    assert _events("item/somethingNew", {"threadId": "thr_1"}, state) == []


# ── replay ────────────────────────────────────────────────────────────


def test_call_id_normalization() -> None:
    long_id = "call_" + "x" * 80
    converted = tape_item_to_inject(
        {"id": long_id, "type": "tool_call", "tool": "shell", "input": {"cmd": "ls"}}
    )
    assert converted is not None
    assert len(converted["call_id"]) <= 64
    assert converted["call_id"] != long_id


def test_inject_items_placeholder_for_missing_output() -> None:
    from datetime import datetime, timezone

    from onyx.db.craft_tape import append_tape_entry
    from onyx.db.models import CraftTapeEntry

    class _FakeResult:
        rowcount = 1

    class _FakeDb:
        def __init__(self) -> None:
            self.rows: list[CraftTapeEntry] = []

        # pretend-add builds the row eagerly for load-side fakes below
        def add(self, row: CraftTapeEntry) -> None:
            row.id = len(self.rows) + 1
            row.created_at = datetime.now(tz=timezone.utc)
            self.rows.append(row)

        def execute(self, *_a, **_k):
            return _FakeResult()

        def scalars(self, *_a, **_k):
            return self.rows

    db = _FakeDb()
    session_id = uuid4()
    append_tape_entry(
        db,
        session_id=session_id,
        turn_index=0,
        kind="harness_message",
        subtype="codex:item/completed",
        runtime="codex",
        payload={
            "item": {
                "id": "call_1",
                "type": "command_execution",
                "tool": "shell",
                "input": {"command": "ls"},
                # no output — interrupted turn
            }
        },
    )
    items = build_inject_items(db, session_id)  # type: ignore[arg-type]
    call = next(i for i in items if i["type"] == "function_call")
    output = next(i for i in items if i["type"] == "function_call_output")
    assert call["call_id"] == output["call_id"]
    assert "interrupted" in output["output"]


# ── config ────────────────────────────────────────────────────────────


def test_config_toml_shape() -> None:
    toml = build_codex_config_toml(
        gateway_base_url="https://gw.internal/v1", model="openai/gpt-x"
    )
    assert 'model = "openai/gpt-x"' in toml
    assert 'wire_api = "chat"' in toml
    assert 'base_url = "https://gw.internal/v1"' in toml
    assert 'approval_policy = "never"' in toml
    assert "[mcp_servers" not in toml  # v1: no external MCP on codex


def test_env_file() -> None:
    assert build_codex_env_file("sk-1") == "ONYX_CODEX_API_KEY=sk-1\n"


def test_thread_params_effort_and_sandbox() -> None:
    params = build_thread_start_params(
        cwd="/workspace/sessions/x",
        base_instructions="AGENTS",
        model="gpt-x",
        reasoning_effort="high",
    )
    assert params["cwd"] == "/workspace/sessions/x"
    assert params["ephemeral"] is True
    assert params["approvalPolicy"] == "never"
    assert params["config"]["model_reasoning_effort"] == "high"
    assert params["config"]["web_search"] == "disabled"
    assert build_turn_input("hi")[0]["type"] == "text"


# ── router activation ─────────────────────────────────────────────────


def test_resolve_turn_runtime_scenario_pin(monkeypatch) -> None:
    from onyx.server.features.build.sandbox.agent_runtime import factory
    from onyx.server.features.build.sandbox.agent_runtime.router import (
        RuntimePurpose,
    )
    from onyx.server.features.build.session.manager import SessionManager

    monkeypatch.setenv("SANDBOX_APPROVED_RUNTIMES", "opencode,codex")
    monkeypatch.setattr(factory, "_router_singleton", None)
    from onyx.server.features.build.sandbox.agent_runtime.models import (
        apply_model_catalog_cache,
    )

    apply_model_catalog_cache(
        [
            SimpleNamespace(
                id="openai/gpt-x",
                provider="openai",
                display_name="GPT X",
                max_input_tokens=128000,
                max_output_tokens=16384,
            )
        ],
        "openai/gpt-x",
    )
    scenario = SimpleNamespace(rules={"runtime": {"runtime": "codex"}})
    session = SimpleNamespace(scenario_id=uuid4(), id=uuid4())

    class _Db:
        def get(self, _model, _pk):
            return scenario

    choice = SessionManager.resolve_turn_runtime(
        SimpleNamespace(_db_session=_Db()),  # type: ignore[arg-type]
        session,  # type: ignore[arg-type]
        purpose=RuntimePurpose.CHAT,
    )
    assert choice.runtime_id == "codex"

    # Without approval the pin degrades to the org default, never errors.
    monkeypatch.setenv("SANDBOX_APPROVED_RUNTIMES", "opencode")
    monkeypatch.setattr(factory, "_router_singleton", None)
    fallback = SessionManager.resolve_turn_runtime(
        SimpleNamespace(_db_session=_Db()),  # type: ignore[arg-type]
        session,  # type: ignore[arg-type]
        purpose=RuntimePurpose.CHAT,
    )
    assert fallback.runtime_id == "opencode"


def test_yield_branch_dispatches_to_codex(monkeypatch) -> None:
    """yield_sandbox_events routes scenario-pinned codex turns to the
    codex branch instead of the opencode path."""
    from onyx.server.features.build.session import manager as manager_mod
    from onyx.server.features.build.session.manager import SessionManager

    session = SimpleNamespace(id=uuid4(), scenario_id=None, user_id=uuid4())
    sandbox_row = SimpleNamespace(id=uuid4())
    routed: list[tuple[Any, str]] = []

    class _StubStreaming:
        @staticmethod
        def load_turn_session(*_a, **_k):
            return session

    monkeypatch.setattr(manager_mod, "_streaming", _StubStreaming)

    fake = SimpleNamespace(
        _db_session=SimpleNamespace(get=lambda *_a, **_k: sandbox_row),
        _sandbox_manager=SimpleNamespace(),
        resolve_turn_runtime=lambda *a, **k: SimpleNamespace(runtime_id="codex"),  # noqa: ARG005
        _yield_codex_events=lambda sandbox, bs, content, interrupt, timeout: (  # noqa: ARG005
            routed.append((sandbox.id, content)) or iter(["sentinel"])
        ),
    )

    out = list(
        SessionManager.yield_sandbox_events(
            fake,  # type: ignore[arg-type]
            sandbox_row.id,
            session.id,
            "hello",
        )
    )
    assert out == ["sentinel"]
    assert routed == [(sandbox_row.id, "hello")]


def test_codex_events_unavailable_backend_yields_error() -> None:
    """No transport on the backend (image without ENABLE_CODEX) → one
    user-visible error packet, no crash."""
    from onyx.server.features.build.packets import ErrorPacket
    from onyx.server.features.build.session.manager import SessionManager

    fake = SimpleNamespace(
        _sandbox_manager=SimpleNamespace(codex_transport=lambda: None)
    )
    events = list(
        SessionManager._yield_codex_events(
            fake,  # type: ignore[arg-type]
            SimpleNamespace(id=uuid4()),
            SimpleNamespace(id=uuid4()),
            "hello",
            None,
            None,
        )
    )
    assert any(isinstance(e, ErrorPacket) for e in events)
