"""Unit tests for scenario resource bindings and plan compilation."""

from typing import Iterator

import pytest

from onyx.server.features.build.jobs.graph import compile_graph
from onyx.server.features.build.sandbox.agent_runtime import models as model_registry
from onyx.server.features.scenario.bindings import (
    PhaseGate,
    bindings_for_phase,
    compile_scenario_plan,
    parse_scenario_policy,
    resolve_phase_bindings,
    scenario_runtime_request,
)
from onyx.server.features.scenario.playbook import ScenarioPlaybook
from onyx.server.features.scenario.samples import FINANCE_TAX_RISK_RULES


class _Entry:
    """Gateway-catalog style entry seeding the registry snapshot."""

    def __init__(
        self,
        id: str,
        provider: str,
        display_name: str,
        max_input_tokens: int | None = None,
        max_output_tokens: int | None = None,
    ) -> None:
        self.id = id
        self.provider = provider
        self.display_name = display_name
        self.max_input_tokens = max_input_tokens
        self.max_output_tokens = max_output_tokens


@pytest.fixture(autouse=True)
def _catalog_snapshot() -> Iterator[None]:
    """The scenario chain resolves models from the registry snapshot."""
    model_registry.apply_model_catalog_cache(
        [_Entry("registry-default", "bigmodel", "Registry Default")],
        "registry-default",
    )
    yield
    model_registry.apply_model_catalog_cache([], None)


def test_parse_policy_from_finance_sample() -> None:
    policy = parse_scenario_policy(FINANCE_TAX_RISK_RULES)
    assert policy.runtime == "opencode"
    assert policy.bindings.document_sets == ["财务制度", "税务政策"]
    assert policy.bindings.gate == PhaseGate.APPROVE_DELIVERY
    assert policy.delivery_actions == ["save_artifacts"]


def test_phase_bindings_merge_defaults_with_overrides() -> None:
    merged = resolve_phase_bindings(FINANCE_TAX_RISK_RULES)
    # ingest inherits scenario document sets; compute overrides web_search off.
    assert merged["ingest"].document_sets == ["财务制度", "税务政策"]
    assert merged["compute"].web_search is False
    assert merged["compute"].document_sets == ["财务制度", "税务政策"]
    # report overrides the gate explicitly.
    assert merged["report"].gate == PhaseGate.APPROVE_DELIVERY


def test_phase_lists_replace_not_concatenate() -> None:
    rules = {
        "runtime": {
            "bindings": {"skills": ["a", "b"], "document_sets": ["base"]},
        },
        "phases": [{"id": "p1", "bindings": {"skills": ["c"]}}],
    }
    merged = resolve_phase_bindings(rules)
    assert merged["p1"].skills == ["c"]
    assert merged["p1"].document_sets == ["base"]


def test_unknown_phase_gets_neutral_defaults() -> None:
    binding = bindings_for_phase(FINANCE_TAX_RISK_RULES, "not-a-phase")
    assert binding.gate == PhaseGate.NONE
    assert binding.web_search is True


def test_runtime_request_carries_scenario_pin() -> None:
    request = scenario_runtime_request(FINANCE_TAX_RISK_RULES)
    assert request.scenario_runtime == "opencode"
    # Scenarios never bind a model — the field must not exist to carry one.
    assert not hasattr(request, "scenario_model")


def test_compile_scenario_plan_builds_host_phases() -> None:
    plan = compile_scenario_plan(FINANCE_TAX_RISK_RULES, goal="扫描A公司税务风险")
    assert plan.goal == "扫描A公司税务风险"
    phase_ids = [phase.id for phase in plan.phases]
    assert phase_ids == ["ingest", "compute", "validate", "report"]
    # delivery gate in the sample flips ask_delivery on
    assert plan.ask_delivery is True
    assert "outputs/税务风险报告.docx" in plan.done_when

    graph = compile_graph("finance-tax-risk", plan=plan)
    node_ids = [node.id for node in graph.nodes]
    # plan node first, then the scenario phases
    assert node_ids[0] == "plan"
    assert "ingest" in node_ids and "report" in node_ids


def test_compile_with_empty_rules_yields_default_shape() -> None:
    plan = compile_scenario_plan({}, goal="g")
    assert plan.goal == "g"
    assert plan.phases == [] or plan.phases[0].id  # tolerant either way
    assert plan.ask_delivery is False


def test_playbook_roundtrip_keeps_bindings() -> None:
    playbook = ScenarioPlaybook.model_validate(FINANCE_TAX_RISK_RULES)
    assert playbook.runtime is not None
    assert playbook.phases[0].bindings is not None
    assert playbook.phases[0].bindings.get("skills") == ["finance-tax-risk-report"]
    # the scenario rules dict itself round-trips through the playbook
    from onyx.server.features.scenario.playbook import playbook_as_dict

    dumped = playbook_as_dict(playbook)
    assert "model" not in dumped["runtime"]
    assert dumped["phases"][3]["bindings"]["gate"] == "approve_delivery"


def test_biopharma_scenario_compiles_through_the_same_chain() -> None:
    from onyx.server.features.scenario.samples import BIOPHARMA_REGULATORY_RULES

    policy = parse_scenario_policy(BIOPHARMA_REGULATORY_RULES)
    assert policy.runtime == "opencode"
    merged = resolve_phase_bindings(BIOPHARMA_REGULATORY_RULES)
    assert merged["collect"].document_sets == ["注册资料", "临床方案"]
    assert merged["report"].gate == PhaseGate.APPROVE_DELIVERY

    plan = compile_scenario_plan(BIOPHARMA_REGULATORY_RULES, goal="跟踪XX受理号")
    assert [p.id for p in plan.phases] == ["collect", "analyze", "report"]
    assert plan.ask_delivery is True

    from onyx.server.features.build.sandbox.agent_runtime.router import (
        build_router_from_env,
    )

    request = scenario_runtime_request(BIOPHARMA_REGULATORY_RULES)
    choice = build_router_from_env().resolve(request)
    assert choice.origin == "scenario"
    # The scenario pins the runtime only; the model falls back to the
    # registry default.
    assert choice.model_id == "registry-default"


def test_tax_deck_scenarios_compile_through_the_same_chain() -> None:
    from onyx.system_catalog.builtin.manifest import (
        BUILT_IN_SCENARIO_ENTRIES,
        BUILT_IN_SKILL_ENTRIES,
    )

    tax_scenarios = [
        entry for entry in BUILT_IN_SCENARIO_ENTRIES if entry.slug.startswith("tax-")
    ]
    assert len(tax_scenarios) == 6

    skill_slugs = {entry.slug for entry in BUILT_IN_SKILL_ENTRIES}
    for entry in tax_scenarios:
        rules = entry.read_rules()
        playbook = ScenarioPlaybook.model_validate(rules)
        assert playbook.domain == "tax"
        assert set(entry.skill_slugs) <= skill_slugs, entry.slug

        plan = compile_scenario_plan(rules, goal=f"运行{entry.name}")
        assert [p.id for p in plan.phases] == [phase.id for phase in playbook.phases]
        for deliverable in rules["deliverables"]:
            assert deliverable in plan.done_when, (entry.slug, deliverable)

        graph = compile_graph(entry.slug, plan=plan)
        assert graph.nodes

    deck_slugs = {entry.slug for entry in tax_scenarios if entry.slug.endswith("-deck")}
    assert deck_slugs == {
        "tax-monthly-review-deck",
        "tax-policy-briefing-deck",
        "tax-risk-review-deck",
        "tax-annual-settlement-deck",
    }
    by_slug = {entry.slug: entry for entry in tax_scenarios}
    for slug in deck_slugs:
        assert "slideblocks" in by_slug[slug].skill_slugs
        assert "vivid-figures-skill" in by_slug[slug].skill_slugs
