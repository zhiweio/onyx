"""Prose skill binding: exact-slug, word-boundary matches only."""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast

from sqlalchemy.orm import Session

import onyx.server.features.build.skill_binding as skill_binding
from onyx.server.features.build.skill_binding import (
    detect_named_skills,
    merge_selected_skills,
)


def _skill(slug: str) -> SimpleNamespace:
    return SimpleNamespace(
        built_in_skill_id=slug,
        name=slug,
    )


def _patch_visible(monkeypatch, slugs: list[str]) -> None:
    monkeypatch.setattr(
        skill_binding,
        "list_runtime_skills_for_user",
        lambda **_kwargs: [_skill(slug) for slug in slugs],
    )


def test_detects_exactly_named_skill(monkeypatch) -> None:
    _patch_visible(monkeypatch, ["financial-report-analysis", "docx"])
    text = (
        "读取资料库 5 份雪龙集团 PDF 财报，按 financial-report-analysis 技能"
        "撰写《2021—2025年度财务报表与主要财税风险分析》报告"
    )
    assert detect_named_skills(_fake_db(), _user(), text) == [
        "financial-report-analysis"
    ]


def test_word_boundary_does_not_match_longer_slug(monkeypatch) -> None:
    _patch_visible(monkeypatch, ["tax-policy-verify", "tax-policy"])
    # "tax-policy-verify" contains "tax-policy" as a substring; the hyphen
    # counts as a word character so only the full slug matches.
    assert detect_named_skills(_fake_db(), _user(), "use tax-policy-verify now") == [
        "tax-policy-verify"
    ]
    assert detect_named_skills(_fake_db(), _user(), "use tax-policy now") == [
        "tax-policy"
    ]


def test_no_match_inside_identifiers_or_empty(monkeypatch) -> None:
    _patch_visible(monkeypatch, ["docx"])
    assert detect_named_skills(_fake_db(), _user(), "mydocxfile") == []
    assert detect_named_skills(_fake_db(), _user(), "") == []
    assert detect_named_skills(_fake_db(), _user(), None) == []


def test_merge_is_order_stable_and_deduped(monkeypatch) -> None:
    _patch_visible(monkeypatch, ["docx", "financial-report-analysis"])
    merged = merge_selected_skills(
        _fake_db(),
        _user(),
        "按 financial-report-analysis 技能写 docx",
        ["financial-report-analysis"],
    )
    assert merged == ["financial-report-analysis", "docx"]


def test_skill_listing_failure_degrades_to_selection(monkeypatch) -> None:
    def _boom(**_kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(skill_binding, "list_runtime_skills_for_user", _boom)
    assert detect_named_skills(_fake_db(), _user(), "use docx") == []
    assert merge_selected_skills(_fake_db(), _user(), "use docx", ["docx"]) == ["docx"]


def _fake_db() -> Session:
    return cast(Session, SimpleNamespace())


def _user() -> SimpleNamespace:
    return SimpleNamespace(id="user-1")
