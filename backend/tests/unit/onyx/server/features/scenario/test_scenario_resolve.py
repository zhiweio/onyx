from types import SimpleNamespace
from typing import cast
from uuid import UUID, uuid4

from onyx.db.models import Scenario
from onyx.db.scenario import resolve_scenario_skill_ids


def _scenario(rules: dict[str, object], skill_ids: list[UUID]) -> SimpleNamespace:
    links = [
        SimpleNamespace(skill_id=skill_id, sort_order=index)
        for index, skill_id in enumerate(skill_ids)
    ]
    return SimpleNamespace(rules=rules, skill_links=links)


def test_resolve_always_and_bound_skills() -> None:
    always = uuid4()
    bound = uuid4()
    scenario = _scenario({"always_skill_ids": [str(always)]}, [bound])
    assert resolve_scenario_skill_ids(cast(Scenario, scenario)) == [always, bound]


def test_resolve_query_contains_any() -> None:
    extra = uuid4()
    scenario = _scenario(
        {
            "always_skill_ids": [],
            "conditional": [
                {
                    "if": {"query_contains_any": ["专利", "patent"]},
                    "add_skill_ids": [str(extra)],
                }
            ],
        },
        [],
    )
    assert resolve_scenario_skill_ids(cast(Scenario, scenario), "查找专利布局") == [
        extra
    ]
    assert resolve_scenario_skill_ids(cast(Scenario, scenario), "普通问询") == []


def test_resolve_intent_matcher() -> None:
    extra = uuid4()
    scenario = _scenario(
        {
            "conditional": [
                {"if": {"intent": "enforcement"}, "add_skill_ids": [str(extra)]}
            ]
        },
        [],
    )
    assert resolve_scenario_skill_ids(
        cast(Scenario, scenario), "enforcement review"
    ) == [extra]
