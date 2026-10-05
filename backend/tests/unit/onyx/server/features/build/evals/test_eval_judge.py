"""Unit tests for the eval judge: deterministic layer, fresh-context LLM
layer, fail-closed behaviour, and score aggregation."""

import json
from typing import Any

import pytest

from onyx.db.enums import CraftEvalCaseStatus
from onyx.server.features.build.evals import judge as judge_module
from onyx.server.features.build.evals.judge import (
    JudgeError,
    _run_deterministic_checks,
    judge_case,
)
from onyx.system_catalog.builtin.evals.loader import (
    EvalCase,
    EvalRubricCriterion,
    EvalValueAnchor,
)


def _case(
    *,
    rubric: tuple[EvalRubricCriterion, ...] = (),
    anchors: tuple[EvalValueAnchor, ...] = (),
    expected: tuple[str, ...] = ("outputs/report.md",),
    contract: str | None = None,
) -> EvalCase:
    return EvalCase(
        slug="unit-case",
        name="unit",
        domain="tax",
        user_prompt="produce the deliverable with enough detail to be judgeable",
        expected_paths=expected,
        value_anchors=anchors,
        rubric=rubric,
        report_contract_slug=contract,
        budget_seconds=300,
    )


class _FakeLLM:
    def __init__(self, payload: Any = None, raise_exc: Exception | None = None):
        self.payload = payload
        self.raise_exc = raise_exc
        self.calls: list[str] = []

    def invoke(self, messages: Any, **kwargs: Any) -> Any:
        self.calls.append(str(messages))
        if self.raise_exc is not None:
            raise self.raise_exc

        class _Choice:
            class message:  # noqa: N801
                content = json.dumps(self.payload, ensure_ascii=False)

        class _Response:
            choice = _Choice()

        return _Response()


def _patch_llm(
    monkeypatch: pytest.MonkeyPatch, llm: _FakeLLM
) -> None:
    monkeypatch.setattr(judge_module, "resolve_judge_llm", lambda: llm)


# ---------------------------------------------------------------------------
# Deterministic layer
# ---------------------------------------------------------------------------


def test_deterministic_existence_and_placeholders() -> None:
    case = _case()
    findings = _run_deterministic_checks(
        case, {"outputs/report.md": "clean report"}
    )
    assert findings["passed"] == findings["total"]
    assert all(f["passed"] for f in findings["findings"])

    findings = _run_deterministic_checks(
        case, {"outputs/report.md": "has {{placeholder}} left"}
    )
    checks = {f["check"]: f for f in findings["findings"]}
    assert not checks["placeholders:outputs/report.md"]["passed"]

    findings = _run_deterministic_checks(case, {})
    checks = {f["check"]: f for f in findings["findings"]}
    assert not checks["exists:outputs/report.md"]["passed"]


def test_deterministic_value_anchors() -> None:
    case = _case(
        expected=("outputs/vat_summary.json",),
        anchors=(
            EvalValueAnchor(
                path="outputs/vat_summary.json",
                json_path="payable_vat",
                equals=203300.0,
            ),
        ),
    )
    artifacts = {
        "outputs/vat_summary.json": json.dumps({"payable_vat": 203300.0})
    }
    findings = _run_deterministic_checks(case, artifacts)
    assert all(f["passed"] for f in findings["findings"])

    # Tolerance allows float formatting noise only.
    artifacts_noise = {
        "outputs/vat_summary.json": json.dumps({"payable_vat": 203300.004})
    }
    findings = _run_deterministic_checks(case, artifacts_noise)
    assert all(f["passed"] for f in findings["findings"])

    artifacts_wrong = {
        "outputs/vat_summary.json": json.dumps({"payable_vat": 203301.0})
    }
    findings = _run_deterministic_checks(case, artifacts_wrong)
    assert any(not f["passed"] for f in findings["findings"])


def test_deterministic_postcheck_runs_real_contract() -> None:
    case = _case(contract="tax_compliance_check")
    # An empty "report" must trip placeholder-free but fail figures and
    # sources checks from the real contract.
    findings = _run_deterministic_checks(case, {"outputs/report.md": "x"})
    checks = {f["check"]: f for f in findings["findings"]}
    assert "postcheck:figures" in checks
    assert not checks["postcheck:figures"]["passed"]
    assert not checks["postcheck:sources"]["passed"]


def test_deterministic_unknown_contract_slug_fails() -> None:
    case = _case(contract="no_such_contract")
    findings = _run_deterministic_checks(case, {"outputs/report.md": "x"})
    checks = {f["check"]: f for f in findings["findings"]}
    assert not checks["postcheck:contract"]["passed"]


# ---------------------------------------------------------------------------
# LLM layer
# ---------------------------------------------------------------------------


def test_judge_case_happy_path_scores_weighted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = _case(
        rubric=(
            EvalRubricCriterion(id="a", criterion="criterion a", weight=3.0),
            EvalRubricCriterion(id="b", criterion="criterion b", weight=1.0),
        )
    )
    _patch_llm(
        monkeypatch,
        _FakeLLM(
            {
                "checks": [
                    {"id": "a", "verdict": "pass", "evidence": "seen"},
                    {"id": "b", "verdict": "fail", "evidence": "missing"},
                ],
                "comment": "ok",
            }
        ),
    )
    judgement = judge_case(case, {"outputs/report.md": "report text"})
    assert judgement.status == CraftEvalCaseStatus.PASS
    # Deterministic (2 finds × weight 2) + a (3) pass + b (1) fail
    # = 7/7... compute: det 2×2=4 weight, 4 passed; a weight 3 passed;
    # b weight 1 failed → 7/8 = 0.875.
    assert judgement.score == pytest.approx(0.875)
    assert judgement.judge["comment"] == "ok"


def test_judge_fail_closed_on_bad_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = _case(
        rubric=(EvalRubricCriterion(id="a", criterion="criterion a"),)
    )
    _patch_llm(monkeypatch, _FakeLLM({"checks": []}))
    judgement = judge_case(case, {"outputs/report.md": "x"})
    assert judgement.status == CraftEvalCaseStatus.ERROR
    assert judgement.score == 0.0
    # Deterministic findings still present for diagnosis.
    assert judgement.deterministic["total"] > 0

    _patch_llm(monkeypatch, _FakeLLM(None, raise_exc=TimeoutError("slow")))
    judgement = judge_case(case, {"outputs/report.md": "x"})
    assert judgement.status == CraftEvalCaseStatus.ERROR


def test_judge_omitted_criterion_counts_as_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = _case(
        rubric=(
            EvalRubricCriterion(id="a", criterion="criterion a"),
            EvalRubricCriterion(id="b", criterion="criterion b"),
        )
    )
    _patch_llm(
        monkeypatch,
        _FakeLLM(
            {"checks": [{"id": "a", "verdict": "pass", "evidence": "e"}]}
        ),
    )
    judgement = judge_case(case, {"outputs/report.md": "x"})
    by_id = {c["id"]: c for c in judgement.judge["checks"]}
    assert by_id["b"]["verdict"] == "fail"
    assert judgement.judge["omitted"] == ["b"]


def test_judge_partial_is_half_credit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = _case(
        rubric=(EvalRubricCriterion(id="a", criterion="criterion a"),)
    )
    _patch_llm(
        monkeypatch,
        _FakeLLM(
            {"checks": [{"id": "a", "verdict": "partial", "evidence": "e"}]}
        ),
    )
    judgement = judge_case(
        case, {"outputs/report.md": "report text with sources line 来源"}
    )
    assert judgement.score == pytest.approx((4 + 0.5) / 5)


def test_judge_error_type_is_exported() -> None:
    assert issubclass(JudgeError, Exception)
