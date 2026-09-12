"""Shared playbook shape for user scenarios and catalog scenario entries.

Stored as JSONB on both ``scenario.rules`` and ``system_scenario.rules``.
Craft writes these keys into ``SCENARIO.md`` and resolves extra skills from
``conditional`` when a user prompt is present.
Unknown keys (for example ``suggested_lanes`` in shipped YAML) are kept so a
round-trip does not drop builtin content.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ScenarioPlaybookPhase(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str = ""
    done_when: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _coerce_string_phase(cls, value: Any) -> Any:
        if isinstance(value, str):
            return {"id": value}
        return value

    @field_validator("done_when", mode="before")
    @classmethod
    def _coerce_done_when(cls, value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, list):
            parts = [str(item).strip() for item in value if str(item).strip()]
            return "; ".join(parts) or None
        text = str(value).strip()
        return text or None


class ScenarioConditionalMatcher(BaseModel):
    model_config = ConfigDict(extra="allow")

    query_contains_any: list[str] | None = None
    intent: str | None = None


class ScenarioConditionalRule(BaseModel):
    """One optional skill binding.

    User scenarios store ``add_skill_ids``. Catalog entries store
    ``add_skill_slugs``; publish rewrites those to IDs on the projection.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    if_: ScenarioConditionalMatcher = Field(
        default_factory=ScenarioConditionalMatcher, alias="if"
    )
    add_skill_ids: list[str] = Field(default_factory=list)
    add_skill_slugs: list[str] = Field(default_factory=list)


class ScenarioPlaybook(BaseModel):
    """Documented playbook keys plus runtime skill-resolution fields."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    domain: str | None = None
    objective: str | None = None
    required_inputs: list[str] = Field(default_factory=list)
    phases: list[ScenarioPlaybookPhase] = Field(default_factory=list)
    deliverables: list[str] = Field(default_factory=list)
    quality_gates: list[str] = Field(default_factory=list)
    refusal_rules: list[str] = Field(default_factory=list)
    always_skill_ids: list[str] = Field(default_factory=list)
    conditional: list[ScenarioConditionalRule] = Field(default_factory=list)


def playbook_as_dict(playbook: ScenarioPlaybook) -> dict[str, Any]:
    """Persist a playbook without empty lists or blank strings."""
    dumped = playbook.model_dump(by_alias=True, exclude_none=True)
    return {key: value for key, value in dumped.items() if value != [] and value != ""}


def collect_conditional_skill_slugs(rules: dict[str, Any] | None) -> list[str]:
    slugs: list[str] = []
    if not rules:
        return slugs
    raw = rules.get("conditional")
    if not isinstance(raw, list):
        return slugs
    for item in raw:
        if not isinstance(item, dict):
            continue
        for slug in item.get("add_skill_slugs") or []:
            text = str(slug).strip()
            if text:
                slugs.append(text)
    return slugs
