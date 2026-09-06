import pytest

from onyx.db.report_template import normalize_report_template_slug
from onyx.error_handling.error_codes import OnyxErrorCode
from onyx.error_handling.exceptions import OnyxError


def test_normalize_report_template_slug() -> None:
    assert normalize_report_template_slug("Compliance Risk") == "compliance_risk"
    assert normalize_report_template_slug("  CMC-Quality  ") == "cmc_quality"


def test_normalize_report_template_slug_rejects_empty() -> None:
    with pytest.raises(OnyxError) as exc:
        normalize_report_template_slug("合规风险")
    assert exc.value.error_code == OnyxErrorCode.INVALID_INPUT
