"""Content contract and render theme for report templates.

A contract-style template replaces the fixed Word skeleton with two structured
parts:

* ``ReportContract`` — what the report must contain (must-answer questions,
  required elements, the soft narrative spine, the component allowlist and
  the completion criteria). It constrains *what is true*, never how the
  report is laid out.
* ``ReportTheme`` — the visual tokens the deterministic renderer applies
  (palette, fonts, cover recipe). It constrains *what looks consistent*.

Both are stored as JSONB on ``report_template`` and ``system_report_template``.
Empty objects mean the legacy layout-reference behaviour.
"""

from __future__ import annotations

import re
from typing import Final, Literal

from pydantic import BaseModel, Field, field_validator

_HEX_COLOR_PATTERN: Final[re.Pattern[str]] = re.compile(r"^(?:[0-9a-fA-F]{6})$")


class ReportTheme(BaseModel):
    """Visual tokens the deterministic docx renderer applies.

    Colors are six-digit RGB hex without the leading ``#`` so they can be
    embedded directly into OOXML attributes.
    """

    model_config = {"extra": "ignore"}

    accent: str = "2E5E8C"
    ink: str = "1F2937"
    muted: str = "6B7280"
    alert: str = "C00000"
    positive: str = "1F7A33"
    band: str = "DEEBF7"
    font_latin: str = "Times New Roman"
    font_east_asia: str = "SimSun"
    heading_font_latin: str = "Arial"
    heading_font_east_asia: str = "Microsoft YaHei"
    cover: Literal["centered", "banner"] = "centered"

    @field_validator("accent", "ink", "muted", "alert", "positive", "band")
    @classmethod
    def _check_hex(cls, value: str) -> str:
        if not _HEX_COLOR_PATTERN.match(value):
            raise ValueError(f"expected a 6-digit hex color, got '{value}'")
        return value.upper()


class ReportContract(BaseModel):
    """What a report produced under this template must contain."""

    model_config = {"extra": "ignore"}

    must_answer: list[str] = Field(default_factory=list)
    required_elements: list[str] = Field(default_factory=list)
    spine: list[str] = Field(default_factory=list)
    components: list[str] = Field(default_factory=list)
    hard_rules: list[str] = Field(default_factory=list)
    completion_criteria: list[str] = Field(default_factory=list)
    min_figures: int = Field(default=0, ge=0, le=100)
    require_toc: bool = True
    require_disclaimer: bool = True

    @field_validator(
        "must_answer",
        "required_elements",
        "spine",
        "components",
        "hard_rules",
        "completion_criteria",
    )
    @classmethod
    def _check_non_empty_items(cls, value: list[str]) -> list[str]:
        for item in value:
            if not item.strip():
                raise ValueError("contract list items must be non-empty")
        return value


# Canonical required-element keys. The renderer postcheck understands these;
# templates may list additional free-form elements, which stay guidance-only.
ELEMENT_SOURCES: Final[str] = "sources"
ELEMENT_DATA_GAPS: Final[str] = "data_gaps"
ELEMENT_DISCLAIMER: Final[str] = "disclaimer"
ELEMENT_KPI_DASHBOARD: Final[str] = "kpi_dashboard"
ELEMENT_RISK_MATRIX: Final[str] = "risk_matrix"
ELEMENT_REMEDIATION: Final[str] = "remediation"
ELEMENT_SUBSEQUENT_EVENTS: Final[str] = "subsequent_events"

# Element key -> human label (used by the frontend and SCENARIO rendering).
ELEMENT_LABELS: Final[dict[str, str]] = {
    ELEMENT_SOURCES: "数据来源清单",
    ELEMENT_DATA_GAPS: "数据缺口说明",
    ELEMENT_DISCLAIMER: "免责声明",
    ELEMENT_KPI_DASHBOARD: "核心指标看板",
    ELEMENT_RISK_MATRIX: "风险矩阵",
    ELEMENT_REMEDIATION: "整改建议清单",
    ELEMENT_SUBSEQUENT_EVENTS: "期后事项",
}

# Renderer component vocabulary. The contract may restrict the allowlist to a
# subset; an empty list means every component is available.
COMPONENT_KPI: Final[str] = "kpi"
COMPONENT_CALLOUT: Final[str] = "callout"
COMPONENT_TABLE: Final[str] = "table"
COMPONENT_FIGURE: Final[str] = "figure"
COMPONENT_TOC: Final[str] = "toc"

ALL_COMPONENTS: Final[tuple[str, ...]] = (
    COMPONENT_KPI,
    COMPONENT_CALLOUT,
    COMPONENT_TABLE,
    COMPONENT_FIGURE,
    COMPONENT_TOC,
)


def parse_contract(raw: dict | None) -> ReportContract:
    """Build a contract from the JSONB column, tolerating empty/legacy rows."""
    if not raw:
        return ReportContract()
    return ReportContract.model_validate(raw)


def parse_theme(raw: dict | None) -> ReportTheme:
    """Build a theme from the JSONB column, tolerating empty/legacy rows."""
    if not raw:
        return ReportTheme()
    return ReportTheme.model_validate(raw)


def validated_contract(raw: dict | None) -> dict:
    """Validate an incoming contract payload; returns the normalized dict.

    Raises ``ValueError`` with a user-readable message on invalid input.
    """
    if not raw:
        return {}
    return parse_contract(raw).model_dump(exclude_none=True)


def validated_theme(raw: dict | None) -> dict:
    """Validate an incoming theme payload; returns the normalized dict."""
    if not raw:
        return {}
    return parse_theme(raw).model_dump(exclude_none=True)


def is_contract_style(raw_contract: dict | None) -> bool:
    """True when the row opts into the contract+renderer scheme."""
    return bool(raw_contract)
