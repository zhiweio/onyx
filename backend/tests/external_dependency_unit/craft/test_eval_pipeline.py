"""External-dependency tests for the craft eval pipeline (P4).

Drives ``run_eval_pipeline`` end-to-end against the real DB with the stub
sandbox backend (same shape as ``test_scheduled_task_executor``): fixture
seeding, headless turn, artifact collection, judging, run aggregation, and
the regression diff against the previous run.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from sqlalchemy import delete
from sqlalchemy.orm import Session

from onyx.db.craft_evals import get_eval_run, get_eval_run_results
from onyx.db.enums import (
    CraftEvalCaseStatus,
    CraftEvalRunStatus,
    CraftEvalRunTrigger,
    SandboxStatus,
)
from onyx.db.models import Sandbox, User
from onyx.server.features.build.evals import pipeline as eval_pipeline
from onyx.server.features.build.evals import runner as eval_runner
from onyx.server.features.build.evals.judge import CaseJudgement
from onyx.server.features.build.evals.runner import ensure_eval_user
from onyx.server.features.build.sandbox.event_schema import (
    TURN_ERROR_CODE_TIMEOUT,
    Error,
    PromptResponse,
)
from onyx.system_catalog.builtin.evals.loader import (
    EvalCase,
    EvalRubricCriterion,
    EvalValueAnchor,
)
from tests.common.craft.stubs import StubSandboxManager

# A tiny synthetic case: keeps the EDU run fast and independent of the
# packaged golden set.
_QUICK_CASE = EvalCase(
    slug="quick-edu-case",
    name="quick",
    domain="tax",
    user_prompt="produce outputs/report.md summarizing the fixture",
    inputs=(),
    expected_paths=("outputs/report.md",),
    rubric=(EvalRubricCriterion(id="only", criterion="the report exists"),),
    budget_seconds=300,
)

_QUICK_CASES = {"quick-edu-case": _QUICK_CASE}

# Bypass skill-payload: encrypted ExternalApp creds break local MIT
# decryption (same reason as the scheduled-task executor tests).
_SKILLS_PATCH_TARGET = (
    "onyx.server.features.build.session.sandbox_lifecycle.build_user_skills_payload"
)


def _configure_stub(stub: StubSandboxManager) -> None:
    stub.health_check_returns = True
    stub.setup_session_workspace_silent = True
    stub.write_sandbox_file_silent = True
    stub.regenerate_session_config_silent = True
    stub.dispose_opencode_instance_silent = True
    stub.relink_session_skills_silent = True


def _seed_eval_user_sandbox(
    db_session: Session,
    sandbox: Any,
) -> None:
    """Give the eval service user a RUNNING sandbox so the runner takes
    the healthy fast path instead of the stub's unconfigured provision."""
    eval_user = ensure_eval_user(db_session)
    # The eval service user persists across tests; drop any sandbox row a
    # previous test left behind so the unique (user_id) constraint holds.
    db_session.execute(delete(Sandbox).where(Sandbox.user_id == eval_user.id))
    db_session.commit()
    sandbox(user=eval_user, status=SandboxStatus.RUNNING)


def _fake_judge(status: CraftEvalCaseStatus, score: float) -> CaseJudgement:
    return CaseJudgement(
        status=status,
        score=score,
        deterministic={
            "findings": [
                {"check": "exists:outputs/report.md", "passed": True, "detail": "x"}
            ],
            "passed": 1,
            "total": 1,
        },
        judge={
            "checks": [{"id": "only", "verdict": "pass" if score >= 0.8 else "fail"}],
        },
    )


@pytest.fixture()
def quick_case_catalog(monkeypatch: pytest.MonkeyPatch) -> dict[str, EvalCase]:
    monkeypatch.setattr(
        eval_pipeline, "load_builtin_eval_cases", lambda: dict(_QUICK_CASES)
    )
    return dict(_QUICK_CASES)


def test_pipeline_happy_path_passes_and_seeds_fixtures(
    db_session: Session,
    test_user: User,
    sandbox: Any,  # noqa: ARG001
    session_manager_with_stub: Any,  # noqa: ARG001
    stub_sandbox_manager: StubSandboxManager,
    monkeypatch: pytest.MonkeyPatch,
    quick_case_catalog: dict[str, EvalCase],  # noqa: ARG001
) -> None:
    monkeypatch.setattr(_SKILLS_PATCH_TARGET, lambda *_: ("", {}))
    monkeypatch.setattr(
        eval_runner,
        "judge_case",
        lambda *_a, **_k: _fake_judge(CraftEvalCaseStatus.PASS, 1.0),
    )
    _seed_eval_user_sandbox(db_session, sandbox)
    _configure_stub(stub_sandbox_manager)
    stub_sandbox_manager.send_message_events = [
        PromptResponse.model_validate({"stopReason": "end_turn"}),
    ]
    stub_sandbox_manager.read_file_returns = b"# report\n\nsources here"

    run, cases = eval_pipeline.create_eval_run_for_cases(
        db_session, trigger=CraftEvalRunTrigger.MANUAL, created_by_user_id=test_user.id
    )
    assert [c.slug for c in cases] == ["quick-edu-case"]
    db_session.commit()

    eval_pipeline.run_eval_pipeline(run.id)

    db_session.expire_all()
    refreshed = get_eval_run(db_session, run.id)
    assert refreshed is not None
    assert refreshed.status == CraftEvalRunStatus.SUCCEEDED
    assert refreshed.score == pytest.approx(1.0)
    assert refreshed.passed_count == 1
    results = get_eval_run_results(db_session, run.id)
    assert len(results) == 1
    result = results[0]
    assert result.status == CraftEvalCaseStatus.PASS
    assert result.score == pytest.approx(1.0)
    assert result.session_id is not None
    assert result.deterministic_findings["total"] == 1
    # The deliverable was read from the sandbox for judging.
    assert stub_sandbox_manager.read_file_count >= 1


def test_pipeline_drive_error_marks_case_error_run_failed(
    db_session: Session,
    test_user: User,  # noqa: ARG001
    sandbox: Any,  # noqa: ARG001
    session_manager_with_stub: Any,  # noqa: ARG001
    stub_sandbox_manager: StubSandboxManager,
    monkeypatch: pytest.MonkeyPatch,
    quick_case_catalog: dict[str, EvalCase],  # noqa: ARG001
) -> None:
    monkeypatch.setattr(_SKILLS_PATCH_TARGET, lambda *_: ("", {}))
    _seed_eval_user_sandbox(db_session, sandbox)
    _configure_stub(stub_sandbox_manager)
    stub_sandbox_manager.send_message_events = [
        Error.model_validate(
            {"code": TURN_ERROR_CODE_TIMEOUT, "message": "turn timed out"}
        ),
    ]

    run, _ = eval_pipeline.create_eval_run_for_cases(
        db_session, trigger=CraftEvalRunTrigger.MANUAL
    )
    db_session.commit()

    eval_pipeline.run_eval_pipeline(run.id)

    db_session.expire_all()
    refreshed = get_eval_run(db_session, run.id)
    assert refreshed is not None
    # All cases ERROR → run FAILED (infra failure, not a quality miss).
    assert refreshed.status == CraftEvalRunStatus.FAILED
    results = get_eval_run_results(db_session, run.id)
    assert results[0].status == CraftEvalCaseStatus.ERROR
    assert "timed out" in (results[0].error_detail or "")


def test_pipeline_regression_diff_against_previous_run(
    db_session: Session,
    test_user: User,  # noqa: ARG001
    sandbox: Any,  # noqa: ARG001
    session_manager_with_stub: Any,  # noqa: ARG001
    stub_sandbox_manager: StubSandboxManager,
    monkeypatch: pytest.MonkeyPatch,
    quick_case_catalog: dict[str, EvalCase],  # noqa: ARG001
) -> None:
    monkeypatch.setattr(_SKILLS_PATCH_TARGET, lambda *_: ("", {}))
    _seed_eval_user_sandbox(db_session, sandbox)
    _configure_stub(stub_sandbox_manager)
    stub_sandbox_manager.send_message_events = [
        PromptResponse.model_validate({"stopReason": "end_turn"}),
    ]
    stub_sandbox_manager.read_file_returns = b"# report"

    # Run 1: everything passes (baseline).
    monkeypatch.setattr(
        eval_runner,
        "judge_case",
        lambda *_a, **_k: _fake_judge(CraftEvalCaseStatus.PASS, 1.0),
    )
    run_one, _ = eval_pipeline.create_eval_run_for_cases(
        db_session, trigger=CraftEvalRunTrigger.MANUAL
    )
    db_session.commit()
    eval_pipeline.run_eval_pipeline(run_one.id)

    # Run 2: same case fails → REGRESSED with a per-case diff entry.
    monkeypatch.setattr(
        eval_runner,
        "judge_case",
        lambda *_a, **_k: _fake_judge(CraftEvalCaseStatus.FAIL, 0.0),
    )
    run_two, _ = eval_pipeline.create_eval_run_for_cases(
        db_session, trigger=CraftEvalRunTrigger.MANUAL
    )
    db_session.commit()
    eval_pipeline.run_eval_pipeline(run_two.id)

    db_session.expire_all()
    refreshed = get_eval_run(db_session, run_two.id)
    assert refreshed is not None
    assert refreshed.status == CraftEvalRunStatus.REGRESSED
    assert refreshed.score == pytest.approx(0.0)
    regressions = refreshed.summary.get("regressions")
    assert isinstance(regressions, list) and len(regressions) == 1
    assert regressions[0]["case"] == "quick-edu-case"
    assert refreshed.summary.get("previous_run_id") == str(run_one.id)


def test_pipeline_missing_case_definition_marks_error(
    db_session: Session,
    test_user: User,  # noqa: ARG001
    sandbox: Any,  # noqa: ARG001
    session_manager_with_stub: Any,  # noqa: ARG001
    stub_sandbox_manager: StubSandboxManager,
    monkeypatch: pytest.MonkeyPatch,
    quick_case_catalog: dict[str, EvalCase],  # noqa: ARG001
) -> None:
    """A case YAML that disappears between run creation and execution
    errors that case instead of wedging the run."""
    monkeypatch.setattr(_SKILLS_PATCH_TARGET, lambda *_: ("", {}))
    _seed_eval_user_sandbox(db_session, sandbox)
    _configure_stub(stub_sandbox_manager)

    run, _ = eval_pipeline.create_eval_run_for_cases(
        db_session, trigger=CraftEvalRunTrigger.MANUAL
    )
    db_session.commit()
    # The catalog "loses" the case after run creation.
    monkeypatch.setattr(eval_pipeline, "load_builtin_eval_cases", lambda: {})

    eval_pipeline.run_eval_pipeline(run.id)

    db_session.expire_all()
    results = get_eval_run_results(db_session, run.id)
    assert results[0].status == CraftEvalCaseStatus.ERROR
    assert "case definition missing" in (results[0].error_detail or "")


def test_create_run_rejects_unknown_slug(
    db_session: Session,
    quick_case_catalog: dict[str, EvalCase],  # noqa: ARG001
) -> None:
    with pytest.raises(KeyError):
        eval_pipeline.create_eval_run_for_cases(
            db_session,
            trigger=CraftEvalRunTrigger.MANUAL,
            case_slugs=["no-such-case"],
        )


def test_deterministic_checks_read_collected_artifact_shape() -> None:
    """The anchor path over the dict shape the runner collects."""
    case = EvalCase(
        slug="anchor-case",
        name="anchor",
        domain="tax",
        user_prompt="produce outputs/summary.json",
        expected_paths=("outputs/summary.json",),
        value_anchors=(
            EvalValueAnchor(
                path="outputs/summary.json", json_path="payable", equals=1.5
            ),
        ),
        rubric=(),
        budget_seconds=300,
    )
    from onyx.server.features.build.evals.judge import (
        _run_deterministic_checks as run_checks,
    )

    findings = run_checks(case, {"outputs/summary.json": json.dumps({"payable": 1.5})})
    assert findings["passed"] == findings["total"]
