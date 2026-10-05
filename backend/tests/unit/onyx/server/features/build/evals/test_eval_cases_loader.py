"""Unit tests for the built-in eval case loader (P4)."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from onyx.system_catalog.builtin.evals.loader import (
    EvalCase,
    EvalCaseInput,
    load_builtin_eval_case,
    load_builtin_eval_cases,
)


def test_builtin_cases_load_and_are_self_contained() -> None:
    cases = load_builtin_eval_cases()
    # The packaged golden set: 4 finance/tax + 2 biomed.
    assert len(cases) == 6
    domains = [case.domain for case in cases.values()]
    assert domains.count("biomed") == 2
    for case in cases.values():
        assert case.user_prompt.strip()
        assert case.expected_paths
        assert case.rubric
        # Every input fixture resolves (asset or inline).
        for item in case.inputs:
            assert item.read().strip(), item.path
        # Rubric ids are unique within a case.
        ids = [c.id for c in case.rubric]
        assert len(ids) == len(set(ids))


def test_vat_case_numbers_reconcile() -> None:
    """The golden fixture must be arithmetically solvable: the prompt's
    anchored values are exactly what the invoices imply.

    Book input (trial balance) 579,400 = deductible 567,700 + welfare
    transfer-out 11,700; payable = output − deductible − prior credit.
    """
    case = load_builtin_eval_case("tax-vat-filing-workpaper-golden")
    anchors = {a.json_path: a.equals for a in case.value_anchors}
    output = float(anchors["output_tax"])  # type: ignore[arg-type]
    transfer = float(anchors["input_tax_transfer_out"])  # type: ignore[arg-type]
    deductible = float(anchors["deductible_input_tax"])  # type: ignore[arg-type]
    credit = float(anchors["prior_period_credit"])  # type: ignore[arg-type]
    payable = float(anchors["payable_vat"])  # type: ignore[arg-type]
    # The trial balance books 579,400 input tax (see fixture CSV).
    assert deductible + transfer == 579400.0
    assert payable == output - deductible - credit
    assert payable == 203300.0


def test_input_rejects_traversal_and_double_source() -> None:
    with pytest.raises(ValidationError):
        EvalCaseInput(path="../escape.csv", content="x")
    with pytest.raises(ValidationError):
        EvalCaseInput(path="/abs/path.csv", content="x")
    with pytest.raises(ValidationError):
        EvalCaseInput(path="inputs/a.csv")
    with pytest.raises(ValidationError):
        EvalCaseInput(path="inputs/a.csv", content="x", file="a.csv")


def test_case_rejects_unsafe_expected_path() -> None:
    base = dict(
        slug="x-case",
        name="x",
        domain="tax",
        user_prompt="do the thing with enough detail",
    )
    with pytest.raises(ValidationError):
        EvalCase.model_validate({**base, "expected_paths": ["../out.md"]})
    with pytest.raises(ValidationError):
        EvalCase.model_validate({**base, "expected_paths": ["outputs//x"]})


def test_assets_live_under_the_evals_package(tmp_path: Path) -> None:
    """Guard against moving the assets dir out from under the loader."""
    cases = load_builtin_eval_cases()
    vat = cases["tax-vat-filing-workpaper-golden"]
    sales = next(i for i in vat.inputs if i.path.endswith("sales_invoices.csv"))
    content = sales.read()
    # A spot-check that fixture content is the synthetic ledger.
    assert "33726000001120000001" in content
