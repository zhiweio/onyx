from __future__ import annotations

from types import SimpleNamespace

from onyx.server.features.build.jobs.protocol import (
    PHASE_DONE_PATH,
    compose_phase_index,
    continuation_prompt,
    current_phase,
    default_phases_for_domain,
    first_phase_prompt,
    phase_index_by_id,
)


def test_default_phases_split_research_and_document() -> None:
    biomed = default_phases_for_domain("biomed")
    tax = default_phases_for_domain("tax")
    assert [phase["id"] for phase in biomed] == [
        "plan",
        "research",
        "compose",
        "review",
    ]
    assert [phase["id"] for phase in tax] == [
        "plan",
        "ingest",
        "analyze",
        "compose",
        "review",
    ]
    assert all(phase["status"] == "pending" for phase in tax)


def test_phase_helpers() -> None:
    phases = default_phases_for_domain("tax")
    assert current_phase(phases, 0)["id"] == "plan"
    assert current_phase(phases, 99) is None
    assert phase_index_by_id(phases, "analyze") == 2
    assert compose_phase_index(phases) == 3


def test_continuation_prompt_names_phase_done() -> None:
    prompt = continuation_prompt(
        phase={"id": "ingest", "name": "Ingest documents"},
        domain="tax",
        job_name="Supplier recon",
    )
    assert "ingest" in prompt
    assert PHASE_DONE_PATH in prompt
    assert "document-ingest" in prompt


def test_first_phase_prompt_includes_user_text() -> None:
    prompt = first_phase_prompt(
        user_prompt="对账批次 2026Q2",
        domain="tax",
        job_name="Supplier recon",
    )
    assert "2026Q2" in prompt
    assert "plan" in prompt


def test_job_turn_budgets_respect_phase_cap(monkeypatch) -> None:
    from onyx.server.features.build.jobs import continuation as continuation_mod
    from onyx.server.features.build.timeouts import INTERACTIVE_TURN_HARD_CAP_SECONDS

    job = SimpleNamespace(phase_budget_seconds=1500)
    monkeypatch.setattr(
        "onyx.server.features.build.configs.CRAFT_DEEP_JOB_RESOURCES", False
    )
    soft, hard = continuation_mod.job_turn_budgets(job)
    assert hard == 1500
    assert hard <= INTERACTIVE_TURN_HARD_CAP_SECONDS
    assert 0 < soft < hard
    assert continuation_mod.job_turn_budgets(None) is None
