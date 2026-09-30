"""Per-persona agent budget resolution: override order, caps, bad-data fallback."""

from __future__ import annotations

import logging

import pytest

from onyx.chat.agent_budget import (
    MAX_EXTENSION_CYCLES_CAP,
    MAX_LLM_CYCLES_CAP,
    AgentBudget,
    resolve_budget,
)


def test_no_persona_budget_inherits_global() -> None:
    budget = resolve_budget(None)
    assert budget.source == "global"
    assert budget.max_llm_cycles == 6
    assert budget.max_extension_cycles >= 0
    assert budget.turn_token_budget >= 0


def test_persona_overrides_apply_field_by_field(monkeypatch) -> None:
    monkeypatch.setattr("onyx.chat.agent_budget.MAX_LLM_CYCLES", 6)
    monkeypatch.setattr("onyx.chat.agent_budget.CHAT_AGENT_MAX_EXTENSION_CYCLES", 6)
    budget = resolve_budget({"max_llm_cycles": 30})
    # Only the provided field is overridden; the rest inherit.
    assert budget.max_llm_cycles == 30
    assert budget.max_extension_cycles == 6
    assert budget.source == "persona"


def test_malformed_payload_falls_back_to_global(caplog) -> None:
    with caplog.at_level(logging.WARNING):
        budget = resolve_budget({"max_llm_cycles": "not-a-number"})
    assert budget.source == "global"
    assert any("agent_budget_parse_failed" in r.message for r in caplog.records)


def test_out_of_caps_payload_falls_back_to_global(caplog) -> None:
    with caplog.at_level(logging.WARNING):
        budget = resolve_budget({"max_llm_cycles": MAX_LLM_CYCLES_CAP + 1})
    assert budget.source == "global"


def test_agent_budget_rejects_bad_values() -> None:
    with pytest.raises(ValueError):
        AgentBudget(max_llm_cycles=0)
    with pytest.raises(ValueError):
        AgentBudget(max_extension_cycles=MAX_EXTENSION_CYCLES_CAP + 1)
    with pytest.raises(ValueError):
        AgentBudget(turn_token_budget=-1)
