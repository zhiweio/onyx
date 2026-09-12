from types import SimpleNamespace
from uuid import uuid4

from onyx.db.enums import ReportTemplateKind
from onyx.server.features.scenario.runtime import (
    apply_scenario_to_turn,
    merge_skill_id_strings,
    render_playbook_section,
    render_scenario_markdown_named,
)


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
        kind=ReportTemplateKind.MARKDOWN,
        placeholders=[],
    )
    monkeypatch.setattr(
        "onyx.server.features.scenario.runtime.get_report_template_by_slug",
        lambda _db, slug: template if slug == "compliance_risk" else None,
    )
    scenario = SimpleNamespace(
        name="合规风险预警",
        description="Tax pack",
        rules={
            "domain": "tax",
            "objective": "Produce a cited tax-compliance risk brief",
            "required_inputs": ["entity", "period"],
            "always_skill_ids": ["should-not-appear"],
        },
        skill_links=[],
        report_template="compliance_risk",
    )
    text = render_scenario_markdown_named(_FakeSession(template), scenario)
    assert "Preferred report template: `compliance_risk`" in text
    assert "Tax compliance risk brief for an entity." in text
    assert "# 合规风险预警报告" in text
    assert "## Domain" in text
    assert "tax" in text
    assert "## Objective" in text
    assert "Produce a cited tax-compliance risk brief" in text
    assert "entity" in text
    assert "always_skill_ids" not in text
    assert "should-not-appear" not in text


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


def test_render_playbook_includes_domain_and_extra_skills() -> None:
    extra = uuid4()
    lines = render_playbook_section(
        {
            "domain": "tax",
            "objective": "Cite the filing.",
            "conditional": [
                {
                    "if": {"query_contains_any": ["专利", "patent"]},
                    "add_skill_ids": [str(extra)],
                },
                {
                    "if": {"intent": "enforcement"},
                    "add_skill_slugs": ["legal-review"],
                },
            ],
        },
        {str(extra): "Patent search", "legal-review": "Legal review"},
    )
    text = "\n".join(lines)
    assert "## Domain" in text
    assert "tax" in text
    assert "## Extra skills" in text
    assert "If the query contains `专利` or `patent`, add `Patent search`" in text
    assert "If the intent is `enforcement`, add `Legal review`" in text


def test_merge_skill_id_strings_keeps_order_and_dedupes() -> None:
    assert merge_skill_id_strings(["a", "b"], ["b", "c", "  "]) == ["a", "b", "c"]


def test_apply_merges_resolved_skills_and_rewrites_md(monkeypatch) -> None:
    extra = uuid4()
    bound = uuid4()
    session_id = uuid4()
    scenario = SimpleNamespace(
        name="Pack",
        description="Desc",
        rules={
            "domain": "tax",
            "conditional": [
                {
                    "if": {"query_contains_any": ["patent"]},
                    "add_skill_ids": [str(extra)],
                }
            ],
        },
        skill_links=[SimpleNamespace(skill_id=bound, sort_order=0)],
        report_template=None,
    )
    monkeypatch.setattr(
        "onyx.server.features.scenario.runtime.get_scenario_for_user",
        lambda *_args, **_kwargs: scenario,
    )
    monkeypatch.setattr(
        "onyx.server.features.scenario.runtime.get_report_template_by_slug",
        lambda *_args, **_kwargs: None,
    )
    written: dict[str, str] = {}

    class _Writer:
        def write_sandbox_file(self, _sandbox_id, path: str, content: str) -> None:
            written[path] = content

    merged = apply_scenario_to_turn(
        _FakeSession(None),
        scenario_id=uuid4(),
        user=SimpleNamespace(),
        query="patent search",
        selected_skill_ids=["user-picked"],
        sandbox_manager=_Writer(),
        sandbox_id=uuid4(),
        session_id=session_id,
    )
    assert merged == [str(bound), str(extra), "user-picked"]
    content = written[f"sessions/{session_id}/SCENARIO.md"]
    assert "## Domain" in content
    assert "## Extra skills" in content
    assert "patent" in content
