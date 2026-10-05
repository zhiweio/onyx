"""Built-in golden-set eval cases for the craft eval pipeline (P4).

Cases live as YAML under ``evals/cases/`` (one file per case) with larger
fixtures under ``evals/assets/``. They are data, not DB rows: the loader
reads them at runtime so a case edit ships with the code and stays
git-versioned. Every case is self-contained — inputs are synthetic and
pre-stage what external retrieval (MCP / web) would return, so a run never
depends on outside services and regression results are reproducible.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

_EVALS_DIR: Final[Path] = Path(__file__).parent
_CASES_DIR: Final[Path] = _EVALS_DIR / "cases"
_ASSETS_DIR: Final[Path] = _EVALS_DIR / "assets"

_SLUG_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_CRITERION_ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


class EvalCaseInput(BaseModel):
    """One fixture file seeded into the session workspace.

    ``path`` is session-relative (e.g. ``inputs/vat/sales.csv``); content
    comes either inline (``content``) or from a packaged asset
    (``file``, relative to ``evals/assets/``). Exactly one must be set.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str = Field(min_length=1, max_length=256)
    content: str | None = None
    file: str | None = None

    @model_validator(mode="after")
    def _check_exactly_one_source(self) -> EvalCaseInput:
        if (self.content is None) == (self.file is None):
            raise ValueError("exactly one of content / file must be set")
        if not _is_safe_relative_path(self.path):
            raise ValueError(f"unsafe input path: {self.path}")
        return self

    def read(self) -> str:
        if self.content is not None:
            return self.content
        assert self.file is not None
        path = _ASSETS_DIR / self.file
        if not path.is_file():
            raise ValueError(f"missing eval asset: {self.file}")
        return path.read_text(encoding="utf-8")


class EvalValueAnchor(BaseModel):
    """Deterministic numeric/string check against a JSON deliverable.

    ``json_path`` is a dot path (numeric segments index lists). The agent
    prompt pins the JSON schema so the anchor is part of the contract.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str = Field(min_length=1)
    json_path: str = Field(min_length=1)
    equals: float | int | str | bool


class EvalRubricCriterion(BaseModel):
    """One fresh-context judge criterion, derived from the scenario's
    quality gates."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(pattern=_CRITERION_ID_PATTERN.pattern, max_length=64)
    criterion: str = Field(min_length=4, max_length=2000)
    weight: float = Field(default=1.0, gt=0, le=10.0)


class EvalCase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    slug: str = Field(pattern=_SLUG_PATTERN.pattern, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    # Display grouping only (tax / finance / biomed).
    domain: str = Field(min_length=2, max_length=32)
    # Informational link to the scenario family this case exercises.
    scenario_slug: str | None = None
    # Extra skills linked into the session beyond the core delivery set.
    skill_slugs: tuple[str, ...] = ()
    # Builtin report-template slug; enables the postcheck layer.
    report_contract_slug: str | None = None
    user_prompt: str = Field(min_length=16)
    inputs: tuple[EvalCaseInput, ...] = ()
    expected_paths: tuple[str, ...] = ()
    value_anchors: tuple[EvalValueAnchor, ...] = ()
    rubric: tuple[EvalRubricCriterion, ...] = ()
    budget_seconds: int = Field(default=1800, ge=300, le=7200)

    @model_validator(mode="after")
    def _validate_paths(self) -> EvalCase:
        for path in self.expected_paths:
            if not _is_safe_relative_path(path):
                raise ValueError(f"unsafe expected path: {path}")
        return self


def _is_safe_relative_path(path: str) -> bool:
    """Reject absolute, traversal, and dot-segment paths."""
    if not path or path.startswith(("/", "~")):
        return False
    parts = path.split("/")
    return all(part not in ("", ".", "..") for part in parts) and (
        "\x00" not in path
    )


def load_builtin_eval_cases() -> dict[str, EvalCase]:
    """All built-in cases keyed by slug (sorted by filename for stable
    ordering). Raises on the first invalid file so a bad case fails
    startup loudly instead of silently skipping."""
    cases: dict[str, EvalCase] = {}
    for path in sorted(_CASES_DIR.glob("*.yaml")):
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(f"Eval case must be a mapping: {path.name}")
        case = EvalCase.model_validate(raw)
        if case.slug in cases:
            raise ValueError(f"duplicate eval case slug: {case.slug}")
        cases[case.slug] = case
    return cases


def load_builtin_eval_case(slug: str) -> EvalCase:
    case = load_builtin_eval_cases().get(slug)
    if case is None:
        raise KeyError(f"unknown eval case: {slug}")
    return case
