"""Skill-binding normalization: turn bindings must carry slugs, never IDs."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from onyx.server.features.build.interactive_turns.executor import (
    _skill_binding_preamble,
)
from onyx.server.features.build.skill_binding import resolve_skill_refs_to_slugs


class _FakeResult:
    def __init__(self, rows: list[tuple]) -> None:
        self._rows = rows

    def all(self) -> list[tuple]:
        return self._rows


class _FakeSession:
    """Minimal stand-in exposing execute(...).all() for the slug lookup."""

    def __init__(self, rows: list[tuple]) -> None:
        self._rows = rows

    def execute(self, *_args: object, **_kwargs: object) -> _FakeResult:
        return _FakeResult(self._rows)


def test_resolve_skill_refs_maps_uuids_to_slugs() -> None:
    bound_id = uuid4()
    other_id = uuid4()
    session = _FakeSession(
        [
            # (id, built_in_skill_id, name) — built_in wins over name.
            (bound_id, "finance-tax-risk-report", "财税与经营风险分析"),
            (other_id, None, "slideblocks"),
        ]
    )
    resolved = resolve_skill_refs_to_slugs(
        session,
        [str(bound_id), "financial-report-analysis", str(other_id), str(bound_id)],
    )
    assert resolved == [
        "finance-tax-risk-report",
        "financial-report-analysis",
        "slideblocks",
    ]


def test_resolve_skill_refs_drops_unknown_ids_and_blanks() -> None:
    session = _FakeSession([])  # no skill rows: every UUID is unresolvable
    resolved = resolve_skill_refs_to_slugs(
        session, [str(uuid4()), "", "  ", "chart-gen"]
    )
    assert resolved == ["chart-gen"]


def test_binding_preamble_lists_slug_paths_with_fallback_note() -> None:
    preamble = _skill_binding_preamble(
        ["finance-tax-risk-report", "vivid-figures-skill"], "做五年风险报告"
    )
    assert ".opencode/skills/`finance-tax-risk-report`/SKILL.md" in preamble.replace(
        "<slug>", "`finance-tax-risk-report`"
    )
    assert "finance-tax-risk-report" in preamble
    assert "vivid-figures-skill" in preamble
    assert "missing" in preamble  # the missing-skill fallback instruction


def test_binding_preamble_empty_and_guard() -> None:
    assert _skill_binding_preamble([], "任意提示") == ""
    assert _skill_binding_preamble(None, "任意提示") == ""
    prompt = "The user explicitly requires the skill(s) already stated."
    assert _skill_binding_preamble(["chart-gen"], prompt) == ""


def test_scenario_markdown_tells_the_agent_to_load_skills(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from onyx.server.features.scenario import runtime as scenario_runtime

    bound_id = uuid4()
    scenario = SimpleNamespace(
        name="财税与经营风险分析",
        description="五年风险报告",
        rules={"always_skill_ids": [str(bound_id)]},
        skill_links=[],
        report_template=None,
    )
    monkeypatch.setattr(
        scenario_runtime,
        "resolve_scenario_skill_ids",
        lambda _scenario, _query: [bound_id],
    )
    monkeypatch.setattr(
        scenario_runtime,
        "skill_name_map",
        lambda _db, _ids: {str(bound_id): "finance-tax-risk-report"},
    )
    markdown = scenario_runtime.render_scenario_markdown_named(
        None,
        scenario,
        None,  # type: ignore[arg-type]
    )
    assert "- finance-tax-risk-report" in markdown
    assert ".opencode/skills/<slug>/SKILL.md" in markdown
