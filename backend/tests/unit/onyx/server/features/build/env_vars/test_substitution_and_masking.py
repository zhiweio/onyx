"""Prompt substitution + run-time secret masking (pure unit)."""

from __future__ import annotations

from acp.schema import AgentMessageChunk
from acp.schema import ToolCallStart as AcpToolCallStart

from onyx.server.features.build.env_vars.masking import (
    MASKED_SECRET,
    SecretMasker,
    mask_sandbox_event,
)
from onyx.server.features.build.env_vars.substitution import (
    extract_env_var_references,
    render_prompt_with_env_vars,
)

# ---------------------------------------------------------------------------
# Substitution
# ---------------------------------------------------------------------------


def test_extract_finds_env_and_secrets_references() -> None:
    prompt = (
        "Call {{env.API_BASE}} with {{ secrets.TOKEN }} "
        "and again {{env.API_BASE}}. Not {{user.name}} or {env.X}."
    )
    assert extract_env_var_references(prompt) == ["API_BASE", "TOKEN"]


def test_render_replaces_known_and_reports_unresolved() -> None:
    prompt = "Key {{secrets.TOKEN}}, base {{ env.API_BASE }}, missing {{env.NOPE}}"
    rendered, unresolved = render_prompt_with_env_vars(
        prompt, {"TOKEN": "sk-1234567890", "API_BASE": "https://api.example.com"}
    )
    assert rendered == (
        "Key sk-1234567890, base https://api.example.com, missing {{env.NOPE}}"
    )
    assert unresolved == ["NOPE"]


def test_render_without_values_reports_every_reference() -> None:
    rendered, unresolved = render_prompt_with_env_vars("{{env.A}} {{secrets.B}}", {})
    assert rendered == "{{env.A}} {{secrets.B}}"
    assert unresolved == ["A", "B"]


def test_render_ignores_user_placeholders() -> None:
    rendered, unresolved = render_prompt_with_env_vars(
        "Hi {{user.email}}", {"email": "x@example.com"}
    )
    assert rendered == "Hi {{user.email}}"
    assert unresolved == []


# ---------------------------------------------------------------------------
# Masking
# ---------------------------------------------------------------------------


def test_masker_replaces_values_longest_first() -> None:
    masker = SecretMasker(["sk-prefix-long-value", "sk-prefix"])
    text = "keys: sk-prefix-long-value and sk-prefix"
    assert masker.mask(text) == f"keys: {MASKED_SECRET} and {MASKED_SECRET}"


def test_masker_inactive_when_no_secrets() -> None:
    masker = SecretMasker([])
    assert masker.active is False
    assert masker.mask("anything") == "anything"


def test_mask_sandbox_event_masks_nested_text() -> None:
    masker = SecretMasker(["sk-super-secret-value"])
    chunk = AgentMessageChunk.model_validate(
        {
            "sessionUpdate": "agent_message_chunk",
            "content": {"type": "text", "text": "token is sk-super-secret-value"},
        }
    )
    masked = mask_sandbox_event(chunk, masker)
    assert getattr(masked.content, "text", None) == f"token is {MASKED_SECRET}"
    # The original event is not mutated in place.
    assert getattr(chunk.content, "text", None) == "token is sk-super-secret-value"


def test_mask_sandbox_event_masks_tool_call_strings() -> None:
    masker = SecretMasker(["sk-super-secret-value"])
    tool_call = AcpToolCallStart.model_validate(
        {
            "sessionUpdate": "tool_call",
            "title": "curl with sk-super-secret-value",
            "kind": "execute",
            "toolCallId": "call-1",
        }
    )
    masked = mask_sandbox_event(tool_call, masker)
    assert masked.title == f"curl with {MASKED_SECRET}"


def test_mask_sandbox_event_passthrough_when_inactive() -> None:
    masker = SecretMasker([])
    chunk = AgentMessageChunk.model_validate(
        {
            "sessionUpdate": "agent_message_chunk",
            "content": {"type": "text", "text": "plain"},
        }
    )
    assert mask_sandbox_event(chunk, masker) is chunk
