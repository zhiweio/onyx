"""Per-persona agent loop budget resolution.

Resolves the chat tool-loop budget for one request: the persona's
``agent_budget`` JSONB overrides the deployment-wide env defaults field by
field (Codex ``ThreadOptions`` semantics). Malformed payloads never break a
chat request — they degrade to the global budget with a warning.

Caps: ``max_llm_cycles <= 40`` and ``max_extension_cycles <= 24`` are enforced
at write time and again at read time, so a hand-crafted row cannot unbound the
loop.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, field_validator

from onyx.configs.chat_configs import (
    CHAT_AGENT_MAX_EXTENSION_CYCLES,
    CHAT_AGENT_TURN_TOKEN_BUDGET,
    MAX_LLM_CYCLES,
)

logger = logging.getLogger(__name__)

MAX_LLM_CYCLES_CAP = 40
MAX_EXTENSION_CYCLES_CAP = 24


class AgentBudget(BaseModel):
    """Validated persona-level budget overrides. ``None`` fields inherit."""

    max_llm_cycles: int | None = None
    max_extension_cycles: int | None = None
    turn_token_budget: int | None = None

    @field_validator("max_llm_cycles")
    @classmethod
    def _cap_llm_cycles(cls, v: int | None) -> int | None:
        if v is not None and (v < 1 or v > MAX_LLM_CYCLES_CAP):
            raise ValueError(f"max_llm_cycles must be within 1..{MAX_LLM_CYCLES_CAP}")
        return v

    @field_validator("max_extension_cycles")
    @classmethod
    def _cap_extension_cycles(cls, v: int | None) -> int | None:
        if v is not None and (v < 1 or v > MAX_EXTENSION_CYCLES_CAP):
            raise ValueError(
                f"max_extension_cycles must be within 1..{MAX_EXTENSION_CYCLES_CAP}"
            )
        return v

    @field_validator("turn_token_budget")
    @classmethod
    def _cap_token_budget(cls, v: int | None) -> int | None:
        # 0 disables the explicit token ceiling; positive values must be sane.
        if v is not None and v < 0:
            raise ValueError("turn_token_budget must be >= 0")
        return v


@dataclass(frozen=True)
class ResolvedBudget:
    max_llm_cycles: int
    max_extension_cycles: int
    turn_token_budget: int  # 0 = no explicit token ceiling
    source: str  # "persona" | "global"


def resolve_budget(persona_budget: dict[str, Any] | None) -> ResolvedBudget:
    """Resolve the effective budget from a persona's ``agent_budget`` JSONB.

    Overrides apply field-by-field; anything absent/malformed inherits the
    global default. Never raises: a malformed payload logs a warning and
    degrades to the global budget.
    """
    overrides: AgentBudget | None = None
    if persona_budget is not None:
        try:
            overrides = AgentBudget.model_validate(persona_budget)
        except Exception:
            logger.warning(
                "agent_budget_parse_failed; falling back to global budget payload=%r",
                persona_budget,
            )

    if overrides is None:
        return ResolvedBudget(
            max_llm_cycles=MAX_LLM_CYCLES,
            max_extension_cycles=CHAT_AGENT_MAX_EXTENSION_CYCLES,
            turn_token_budget=CHAT_AGENT_TURN_TOKEN_BUDGET,
            source="global",
        )

    return ResolvedBudget(
        max_llm_cycles=(
            overrides.max_llm_cycles
            if overrides.max_llm_cycles is not None
            else MAX_LLM_CYCLES
        ),
        max_extension_cycles=(
            overrides.max_extension_cycles
            if overrides.max_extension_cycles is not None
            else CHAT_AGENT_MAX_EXTENSION_CYCLES
        ),
        turn_token_budget=(
            overrides.turn_token_budget
            if overrides.turn_token_budget is not None
            else CHAT_AGENT_TURN_TOKEN_BUDGET
        ),
        source="persona",
    )
