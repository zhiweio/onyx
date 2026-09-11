from onyx.server.features.scenario.playbook import (
    ScenarioPlaybook,
    collect_conditional_skill_slugs,
    playbook_as_dict,
)


def test_playbook_keeps_unknown_keys_and_drops_empty_lists() -> None:
    playbook = ScenarioPlaybook.model_validate(
        {
            "domain": "biomed",
            "objective": "Reach a cited decision",
            "required_inputs": [],
            "suggested_lanes": [{"role": "literature", "skill_id": "biomed-literature"}],
            "phases": [{"id": "collect", "done_when": ["outputs/a", "outputs/b"]}],
        }
    )
    dumped = playbook_as_dict(playbook)
    assert dumped["domain"] == "biomed"
    assert dumped["objective"] == "Reach a cited decision"
    assert dumped["phases"] == [
        {"id": "collect", "done_when": "outputs/a; outputs/b"}
    ]
    assert dumped["suggested_lanes"] == [
        {"role": "literature", "skill_id": "biomed-literature"}
    ]
    assert "required_inputs" not in dumped


def test_conditional_uses_if_alias_and_collects_slugs() -> None:
    playbook = ScenarioPlaybook.model_validate(
        {
            "conditional": [
                {
                    "if": {"intent": "litigation", "query_contains_any": ["sue"]},
                    "add_skill_slugs": ["qichacha", ""],
                }
            ]
        }
    )
    dumped = playbook_as_dict(playbook)
    assert dumped["conditional"][0]["if"]["intent"] == "litigation"
    assert collect_conditional_skill_slugs(dumped) == ["qichacha"]
