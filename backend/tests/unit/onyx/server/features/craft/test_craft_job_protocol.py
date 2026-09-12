from __future__ import annotations

from types import SimpleNamespace

from onyx.server.features.build.jobs.protocol import (
    compose_phase_index,
    continuation_prompt,
    current_phase,
    default_phases_for_domain,
    first_phase_prompt,
    phase_index_by_id,
)


def test_default_phases_are_domain_agnostic_skeleton() -> None:
    biomed = default_phases_for_domain("biomed")
    tax = default_phases_for_domain("tax")
    general = default_phases_for_domain("general")
    assert [phase["id"] for phase in biomed] == ["plan"]
    assert [phase["id"] for phase in tax] == ["plan"]
    assert [phase["id"] for phase in general] == ["plan"]
    assert all(phase["status"] == "pending" for phase in tax)


def test_phase_helpers() -> None:
    phases = default_phases_for_domain("tax")
    assert current_phase(phases, 0)["id"] == "plan"
    assert current_phase(phases, 99) is None
    assert phase_index_by_id(phases, "compose") is None
    assert compose_phase_index(phases) == 0


def test_continuation_prompt_names_phase_done() -> None:
    prompt = continuation_prompt(
        phase={"id": "ingest", "name": "Ingest documents"},
        domain="tax",
        job_name="Supplier recon",
    )
    assert "ingest" in prompt
    assert "Current node: `ingest`" in prompt
    assert "DONE.json" in prompt
    assert "user-visible reply" in prompt.lower()


def test_first_phase_prompt_includes_user_text() -> None:
    prompt = first_phase_prompt(
        user_prompt="对账批次 2026Q2",
        domain="tax",
        job_name="Supplier recon",
    )
    assert "2026Q2" in prompt
    assert "plan" in prompt
    assert "PLAN.json" in prompt
    assert "lanes [{role" in prompt
    assert "ask_delivery boolean" in prompt


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


def test_job_turn_budgets_use_deep_job_soft_fraction(monkeypatch) -> None:
    from onyx.server.features.build.jobs import continuation as continuation_mod
    from onyx.server.features.build.timeouts import INTERACTIVE_TURN_HARD_CAP_SECONDS

    job = SimpleNamespace(phase_budget_seconds=1500)
    monkeypatch.setattr(
        "onyx.server.features.build.configs.CRAFT_DEEP_JOB_RESOURCES", True
    )
    monkeypatch.setattr(
        "onyx.server.features.build.configs.CRAFT_DEEP_JOB_SOFT_BUDGET_FRACTION",
        0.75,
    )
    soft, hard = continuation_mod.job_turn_budgets(job)
    assert hard == 1500
    assert hard <= INTERACTIVE_TURN_HARD_CAP_SECONDS
    assert soft == 1125


def test_deep_job_inactivity_default_uses_long_tool_window() -> None:
    from onyx.server.features.build.configs import (
        OPENCODE_LONG_TOOL_INACTIVITY_TIMEOUT_SECONDS,
        compute_opencode_inactivity_default,
    )

    approval = 200.0
    assert (
        compute_opencode_inactivity_default(
            deep_job=False, approval_default=approval
        )
        == approval
    )
    assert compute_opencode_inactivity_default(
        deep_job=True, approval_default=approval
    ) == max(approval, OPENCODE_LONG_TOOL_INACTIVITY_TIMEOUT_SECONDS)
