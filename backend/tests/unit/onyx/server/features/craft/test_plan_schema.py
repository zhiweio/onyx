"""PLAN.json accept / reject cases."""

from __future__ import annotations

import pytest

from onyx.server.features.build.jobs.plan import (
    DONE_JSON_PATH,
    PLAN_JSON_PATH,
    apply_plan_to_job_phases,
    parse_plan,
)
from onyx.server.features.build.jobs.protocol import infer_job_domain


def test_skeleton_graph_is_plan_only() -> None:
    from onyx.server.features.build.jobs.graph import compile_graph

    for domain in ("biomed", "tax", "general", ""):
        kinds = [node.kind for node in compile_graph(domain).nodes]
        assert kinds == ["plan"]
        assert compile_graph(domain).get("plan") is not None
        assert compile_graph(domain).get("plan").hitl == "none"


def test_goal_only_plan_compiles_to_work() -> None:
    from onyx.server.features.build.jobs.graph import compile_graph

    plan = parse_plan({"goal": "Ship the dashboard"})
    assert [node.id for node in compile_graph("", plan).nodes] == ["plan", "work"]
    work = compile_graph("", plan).get("work")
    assert work is not None
    assert work.required_paths == [DONE_JSON_PATH]


def test_work_kind_does_not_default_to_done_json() -> None:
    from onyx.server.features.build.jobs.plan import default_done_when

    assert default_done_when("scope", "work") == []
    assert default_done_when("analyze", "analyze") == []


def test_compile_graph_uses_plan_lanes() -> None:
    from onyx.server.features.build.configs import CRAFT_DEEP_JOB_MAX_SPECIALISTS
    from onyx.server.features.build.jobs.graph import compile_graph

    plan = parse_plan(
        {
            "goal": "GLP-1 initiation",
            "lanes": [
                {"role": "literature", "skill_id": "biomed-literature"},
                {"role": "clinical"},
                {"role": "xlsx_parser", "output_dir": "outputs/lanes/xlsx_parser"},
            ],
        }
    )
    graph = compile_graph("biomed", plan)
    lanes = [node for node in graph.nodes if node.kind == "lane"]
    assert [node.role for node in lanes] == ["literature", "clinical", "xlsx_parser"]
    assert lanes[0].skill_id == "biomed-literature"
    assert lanes[0].required_paths == ["outputs/lanes/literature/NOTES.md"]
    assert len(lanes) <= CRAFT_DEEP_JOB_MAX_SPECIALISTS
    assert [node.id for node in graph.nodes] == [
        "plan",
        "lane:literature",
        "lane:clinical",
        "lane:xlsx_parser",
        "reconcile",
        "work",
    ]


def test_compile_graph_compose_review_skips_default_work() -> None:
    from onyx.server.features.build.jobs.graph import compile_graph

    plan = parse_plan(
        {
            "goal": "GLP-1 initiation",
            "lanes": [
                {"role": "literature", "output_dir": "outputs/lanes/literature"}
            ],
            "phases": [
                {"id": "plan", "kind": "plan"},
                {
                    "id": "compose",
                    "kind": "compose",
                    "done_when": ["outputs/markdown/report.md"],
                },
                {"id": "review", "kind": "review"},
            ],
        }
    )
    graph = compile_graph("biomed", plan)
    ids = [node.id for node in graph.nodes]
    assert "work" not in ids
    assert ids == [
        "plan",
        "lane:literature",
        "reconcile",
        "compose",
        "review",
    ]
    literature = graph.get("lane:literature")
    assert literature is not None
    assert literature.required_paths == ["outputs/lanes/literature/NOTES.md"]
    assert not any(
        "outputs/research" in path
        for node in graph.nodes
        for path in node.required_paths
    )


def test_compile_graph_lanes_without_phases_do_not_invent_research() -> None:
    from onyx.server.features.build.jobs.graph import compile_graph

    plan = parse_plan(
        {
            "goal": "Ship notes",
            "lanes": [{"role": "literature"}],
        }
    )
    graph = compile_graph("", plan)
    literature = graph.get("lane:literature")
    assert literature is not None
    assert literature.required_paths == ["outputs/lanes/literature/NOTES.md"]
    assert not any(
        "outputs/research" in path
        for node in graph.nodes
        for path in node.required_paths
    )


def test_compile_graph_uses_model_phases() -> None:
    from onyx.server.features.build.jobs.graph import compile_graph

    plan = parse_plan(
        {
            "goal": "Build the app",
            "phases": [
                {"id": "plan", "kind": "plan"},
                {
                    "id": "implement",
                    "kind": "work",
                    "done_when": ["project/app/main.py"],
                },
                {"id": "test", "kind": "verify", "done_when": ["outputs/test.log"]},
            ],
        }
    )
    graph = compile_graph("", plan)
    assert [node.id for node in graph.nodes] == ["plan", "implement", "test"]
    assert graph.get("test") is not None
    assert graph.get("test").kind == "work"
    assert graph.get("compose") is None
    assert graph.get("review") is None


def test_compile_graph_tax_lanes() -> None:
    from onyx.server.features.build.jobs.graph import compile_graph

    plan = parse_plan(
        {
            "goal": "Reconcile invoices",
            "lanes": [
                {"role": "xlsx_parser", "skill_id": "tax-recon-supplier"},
                {"role": "reconcilier"},
            ],
        }
    )
    graph = compile_graph("tax", plan)
    assert [node.id for node in graph.nodes] == [
        "plan",
        "lane:xlsx_parser",
        "lane:reconcilier",
        "reconcile",
        "work",
    ]
    assert graph.get("lane:xlsx_parser") is not None
    assert graph.get("lane:xlsx_parser").skill_id == "tax-recon-supplier"


def test_suggested_lanes_are_hints_only() -> None:
    from onyx.server.features.build.jobs.graph import compile_graph
    from onyx.server.features.build.jobs.protocol import suggested_lanes_from_rules

    hints = suggested_lanes_from_rules(
        {
            "suggested_lanes": [
                {"role": "literature", "skill_id": "biomed-literature"},
                {"role": "clinical"},
            ]
        }
    )
    assert [item["role"] for item in hints] == ["literature", "clinical"]
    kinds = [node.kind for node in compile_graph("biomed").nodes]
    assert "lane" not in kinds
    assert "research_lane" not in kinds


def test_compile_graph_adds_ingest_when_plan_has_inputs() -> None:
    from onyx.server.features.build.jobs.graph import compile_graph

    plan = parse_plan(
        {
            "goal": "Reconcile invoices",
            "inputs": ["attachments/ledger.xlsx"],
        }
    )
    kinds = [node.kind for node in compile_graph("tax", plan).nodes]
    assert kinds == ["plan", "ingest", "work"]


def test_rejects_too_many_lanes() -> None:
    from onyx.server.features.build.configs import CRAFT_DEEP_JOB_MAX_SPECIALISTS

    lanes = [
        {"role": f"role_{index}", "output_dir": f"outputs/lanes/role_{index}"}
        for index in range(CRAFT_DEEP_JOB_MAX_SPECIALISTS + 1)
    ]
    with pytest.raises(ValueError, match="lanes"):
        parse_plan({"goal": "x", "lanes": lanes})


def test_infer_job_domain_is_explicit_only() -> None:
    assert infer_job_domain("", "biomed") == "biomed"
    assert (
        infer_job_domain("撰写一份 GLP-1 受体激动剂创新药立项深度研究报告")
        == "general"
    )
    assert infer_job_domain("Analyze my dashboard") == "general"
    assert infer_job_domain("税务对账", None) == "general"


def test_accepts_minimal_tax_plan() -> None:
    plan = parse_plan(
        {
            "goal": "Reconcile Q2 invoices",
            "phases": [
                {
                    "id": "plan",
                    "kind": "plan",
                    "done_when": [PLAN_JSON_PATH],
                },
                {
                    "id": "analyze",
                    "kind": "work",
                    "done_when": ["outputs/exceptions/gaps.csv"],
                },
            ],
            "lanes": [
                {
                    "role": "xlsx_parser",
                    "questions": ["Parse the ledger"],
                    "output_dir": "project/research/xlsx_parser",
                }
            ],
            "inputs": ["attachments/ledger.xlsx"],
        }
    )
    assert plan.lanes[0].done_path() == "project/research/xlsx_parser/NOTES.md"


def test_accepts_biomed_plan_with_lanes() -> None:
    plan = parse_plan(
        {
            "goal": "CMC literature sweep",
            "phases": [{"id": "research", "kind": "work", "done_when": []}],
            "lanes": [
                {
                    "role": "literature",
                    "output_dir": "project/research/literature",
                }
            ],
        }
    )
    assert plan.lanes[0].role == "literature"


def test_accepts_work_phase_without_file_done_when() -> None:
    plan = parse_plan(
        {
            "goal": "x",
            "phases": [{"id": "analyze", "kind": "work"}],
        }
    )
    assert plan.phases[0].done_when == []


def test_accepts_prose_done_when_as_empty() -> None:
    plan = parse_plan(
        {
            "goal": "GLP-1 创新药立项",
            "phases": [
                {
                    "id": "plan",
                    "kind": "plan",
                    "done_when": "TPP 与决策问题已写入固定问题清单",
                },
                {
                    "id": "literature",
                    "kind": "work",
                    "done_when": "每个文献问题都有出处",
                },
            ],
        }
    )
    assert plan.phases[0].done_when == []
    assert plan.phases[1].done_when == []


def test_rejects_path_escape() -> None:
    with pytest.raises(ValueError, match="Unsafe"):
        parse_plan(
            {
                "goal": "x",
                "phases": [
                    {
                        "id": "plan",
                        "kind": "plan",
                        "done_when": ["../etc/passwd"],
                    }
                ],
            }
        )


def test_accepts_canonical_lane_output_dir() -> None:
    plan = parse_plan(
        {
            "goal": "x",
            "lanes": [{"role": "a", "output_dir": "outputs/lanes/a"}],
        }
    )
    assert plan.lanes[0].done_path() == "outputs/lanes/a/NOTES.md"


def test_accepts_legacy_research_output_dir() -> None:
    plan = parse_plan(
        {
            "goal": "x",
            "lanes": [{"role": "a", "output_dir": "outputs/research/a"}],
        }
    )
    assert plan.lanes[0].done_path() == "outputs/research/a/NOTES.md"


def test_rejects_scratch_lane_dir() -> None:
    with pytest.raises(ValueError, match="output_dir"):
        parse_plan(
            {
                "goal": "x",
                "lanes": [{"role": "a", "output_dir": "outputs/tmp/a"}],
            }
        )


def test_apply_plan_copies_phase_done_when() -> None:
    plan = parse_plan(
        {
            "goal": "x",
            "phases": [
                {"id": "plan", "kind": "plan", "done_when": [PLAN_JSON_PATH]},
                {
                    "id": "build",
                    "kind": "work",
                    "done_when": ["project/app/main.py"],
                },
            ],
        }
    )
    updated = apply_plan_to_job_phases(
        [
            {"id": "plan", "kind": "plan", "status": "succeeded"},
            {"id": "build", "kind": "work", "status": "pending"},
        ],
        plan,
    )
    assert updated[1]["done_when"] == ["project/app/main.py"]
    assert "NOTES.md" not in "".join(updated[1]["done_when"])


def test_lane_done_when_sets_required_paths() -> None:
    from onyx.server.features.build.jobs.graph import compile_graph

    plan = parse_plan(
        {
            "goal": "GLP-1",
            "lanes": [
                {
                    "role": "biomed-literature",
                    "done_when": ["outputs/research/literature/NOTES.md"],
                }
            ],
        }
    )
    assert plan.lanes[0].output_dir == "outputs/research/literature"
    assert plan.lanes[0].skill_id == "biomed-literature"
    assert plan.lanes[0].required_paths() == [
        "outputs/research/literature/NOTES.md"
    ]
    graph = compile_graph("", plan)
    literature = graph.get("lane:biomed-literature")
    assert literature is not None
    assert literature.required_paths == ["outputs/research/literature/NOTES.md"]
    assert literature.skill_id == "biomed-literature"


def test_ask_delivery_does_not_duplicate_review() -> None:
    from onyx.server.features.build.jobs.graph import compile_graph

    plan = parse_plan(
        {
            "goal": "GLP-1",
            "lanes": [{"role": "literature"}],
            "phases": [
                {
                    "id": "compose",
                    "kind": "work",
                    "done_when": ["outputs/markdown/initiation-report.md"],
                },
                {
                    "id": "review",
                    "kind": "work",
                    "done_when": ["outputs/DONE.json"],
                },
            ],
            "ask_delivery": True,
        }
    )
    ids = [node.id for node in compile_graph("", plan).nodes]
    assert ids.count("review") == 1
    review = compile_graph("", plan).get("review")
    assert review is not None
    assert review.hitl == "approve_delivery"
    assert review.required_paths == ["outputs/DONE.json"]
    assert "review-2" not in ids
