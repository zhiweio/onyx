from types import SimpleNamespace
from uuid import uuid4

from onyx.server.features.scenario.runtime import render_scenario_markdown_named


class _FakeSession:
    def __init__(self, template) -> None:
        self.template = template

    def scalars(self, _stmt):
        return SimpleNamespace(all=lambda: [])

    def scalar(self, _stmt):
        return self.template


def test_render_includes_template_body(monkeypatch) -> None:
    template = SimpleNamespace(
        description="Tax compliance risk brief for an entity.",
        body="# 合规风险预警报告\n\n1. **对象**",
    )
    monkeypatch.setattr(
        "onyx.server.features.scenario.runtime.get_report_template_by_slug",
        lambda _db, slug: template if slug == "compliance_risk" else None,
    )
    scenario = SimpleNamespace(
        name="合规风险预警",
        description="Tax pack",
        rules={},
        skill_links=[],
        report_template="compliance_risk",
    )
    text = render_scenario_markdown_named(_FakeSession(template), scenario)
    assert "Preferred report template: `compliance_risk`" in text
    assert "Tax compliance risk brief for an entity." in text
    assert "# 合规风险预警报告" in text


def test_render_keeps_slug_when_template_missing(monkeypatch) -> None:
    monkeypatch.setattr(
        "onyx.server.features.scenario.runtime.get_report_template_by_slug",
        lambda _db, _slug: None,
    )
    skill_id = uuid4()
    scenario = SimpleNamespace(
        name="Orphan",
        description="",
        rules={},
        skill_links=[SimpleNamespace(skill_id=skill_id, sort_order=0)],
        report_template="missing_slug",
    )
    text = render_scenario_markdown_named(_FakeSession(None), scenario)
    assert "Preferred report template: `missing_slug`" in text
    assert "# missing_slug" not in text
