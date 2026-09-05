from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from onyx.db.models import Scenario, Skill, User
from onyx.db.scenario import get_scenario_for_user, resolve_scenario_skill_ids
from onyx.server.features.build.sandbox.base import SandboxManager


def render_scenario_markdown(scenario: Scenario, query: str | None = None) -> str:
    skill_ids = resolve_scenario_skill_ids(scenario, query)
    lines = [
        f"# Scenario: {scenario.name}",
        "",
        scenario.description or "",
        "",
        "Use only the skills listed below for this session, unless the user asks otherwise.",
        "",
        "## Skills",
    ]
    if skill_ids:
        for skill_id in skill_ids:
            lines.append(f"- `{skill_id}`")
    else:
        lines.append("- (no skills bound)")
    if scenario.rules:
        lines.extend(["", "## Rules", "", "```json", str(scenario.rules), "```"])
    if scenario.report_template:
        lines.extend(["", f"Report template: `{scenario.report_template}`"])
    return "\n".join(lines).strip() + "\n"


def skill_names_for_ids(db_session: Session, skill_ids: list[UUID]) -> list[str]:
    if not skill_ids:
        return []
    rows = db_session.scalars(select(Skill).where(Skill.id.in_(skill_ids))).all()
    by_id = {row.id: row.name for row in rows}
    return [by_id[skill_id] for skill_id in skill_ids if skill_id in by_id]


def render_scenario_markdown_named(
    db_session: Session, scenario: Scenario, query: str | None = None
) -> str:
    skill_ids = resolve_scenario_skill_ids(scenario, query)
    names = skill_names_for_ids(db_session, skill_ids)
    lines = [
        f"# Scenario: {scenario.name}",
        "",
        scenario.description or "",
        "",
        "Use only these skills unless the user asks otherwise:",
        "",
    ]
    if names:
        lines.extend(f"- {name}" for name in names)
    else:
        lines.append("- (no skills bound)")
    if scenario.report_template:
        lines.extend(["", f"Preferred report template: `{scenario.report_template}`"])
    return "\n".join(lines).strip() + "\n"


def write_scenario_md_to_session(
    db_session: Session,
    sandbox_manager: SandboxManager,
    sandbox_id: UUID,
    session_id: UUID,
    scenario_id: UUID,
    user: User,
) -> None:
    scenario = get_scenario_for_user(db_session, scenario_id, user)
    content = render_scenario_markdown_named(db_session, scenario)
    sandbox_manager.write_sandbox_file(
        sandbox_id, f"sessions/{session_id}/SCENARIO.md", content
    )
