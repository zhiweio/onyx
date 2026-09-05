"""PLAN.json accept / reject cases."""

from __future__ import annotations

import pytest

from onyx.server.features.build.jobs.plan import (
    PLAN_JSON_PATH,
    apply_plan_to_job_phases,
    parse_plan,
)


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
    assert plan.lanes[0].done_path() == "project/research/xlsx_parser/FINDINGS.md"


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


def test_rejects_missing_done_when_without_lanes() -> None:
    with pytest.raises(ValueError, match="done_when"):
        parse_plan(
            {
                "goal": "x",
                "phases": [{"id": "analyze", "kind": "work"}],
            }
        )


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


def test_rejects_lane_outside_research() -> None:
    with pytest.raises(ValueError, match="output_dir"):
        parse_plan(
            {
                "goal": "x",
                "phases": [{"id": "plan", "kind": "plan"}],
                "lanes": [
                    {"role": "a", "output_dir": "outputs/research/a"},
                ],
            }
        )


def test_apply_plan_adds_lane_files_to_work_phase() -> None:
    plan = parse_plan(
        {
            "goal": "x",
            "phases": [
                {"id": "plan", "kind": "plan", "done_when": [PLAN_JSON_PATH]},
                {"id": "analyze", "kind": "analyze"},
            ],
            "lanes": [
                {"role": "a", "output_dir": "project/research/a"},
                {"role": "b", "output_dir": "project/research/b"},
            ],
        }
    )
    updated = apply_plan_to_job_phases(
        [
            {"id": "plan", "kind": "plan", "status": "succeeded"},
            {"id": "analyze", "kind": "analyze", "status": "pending"},
        ],
        plan,
    )
    assert "project/research/a/FINDINGS.md" in updated[1]["done_when"]
    assert "project/research/b/FINDINGS.md" in updated[1]["done_when"]
