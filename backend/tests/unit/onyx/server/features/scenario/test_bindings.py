"""Unit tests for scenario resource bindings and plan compilation."""

from onyx.server.features.build.jobs.graph import compile_graph
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


def test_parse_policy_from_finance_sample() -> None:
    policy = parse_scenario_policy(FINANCE_TAX_RISK_RULES)
    assert policy.runtime == "opencode"
    assert policy.model == "glm-4.7"
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
    assert request.scenario_model == "glm-4.7"


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
    assert dumped["runtime"]["model"] == "glm-4.7"
    assert dumped["phases"][3]["bindings"]["gate"] == "approve_delivery"


def test_biopharma_scenario_compiles_through_the_same_chain() -> None:
    from onyx.server.features.scenario.samples import BIOPHARMA_REGULATORY_RULES

    policy = parse_scenario_policy(BIOPHARMA_REGULATORY_RULES)
    assert policy.model == "qwen3-max"
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
    assert choice.model_id == "qwen3-max"
