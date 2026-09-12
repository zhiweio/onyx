from typing import Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from onyx.db.enums import ReportTemplateKind
from onyx.db.models import ReportTemplate, Scenario, Skill, User
from onyx.db.report_template import get_report_template_by_slug
from onyx.db.scenario import get_scenario_for_user, resolve_scenario_skill_ids
from onyx.report_templates.placeholders import (
    normalize_placeholder_schema,
    table_collections,
)
from onyx.report_templates.sandbox_assets import (
    agent_template_path,
    push_report_templates_to_sandbox,
)
from onyx.server.features.build.sandbox.base import SandboxManager
from onyx.utils.logger import setup_logger

logger = setup_logger()


class _WorkspaceWriter(Protocol):
    def write_sandbox_file(
        self, sandbox_id: UUID, path: str, content: str
    ) -> None: ...


def _scenario_header(name: str, description: str) -> list[str]:
    return [
        f"# Scenario: {name}",
        "",
        description or "",
        "",
        "Use only these skills unless the user asks otherwise:",
        "",
    ]


def render_scenario_markdown(scenario: Scenario, query: str | None = None) -> str:
    skill_ids = resolve_scenario_skill_ids(scenario, query)
    lines = _scenario_header(scenario.name, scenario.description or "")
    if skill_ids:
        lines.extend(f"- `{skill_id}`" for skill_id in skill_ids)
    else:
        lines.append("- (no skills bound)")
    lines.extend(render_playbook_section(scenario.rules or {}))
    if scenario.report_template:
        lines.extend(["", f"Preferred report template: `{scenario.report_template}`"])
    return "\n".join(lines).strip() + "\n"


def skill_name_map(db_session: Session, skill_ids: list[UUID]) -> dict[str, str]:
    if not skill_ids:
        return {}
    rows = db_session.scalars(select(Skill).where(Skill.id.in_(skill_ids))).all()
    return {str(row.id): row.name for row in rows}


def skill_names_for_ids(db_session: Session, skill_ids: list[UUID]) -> list[str]:
    labels = skill_name_map(db_session, skill_ids)
    return [labels[str(skill_id)] for skill_id in skill_ids if str(skill_id) in labels]


def _skill_label(raw: object, labels: dict[str, str] | None) -> str:
    key = str(raw).strip()
    if not key:
        return ""
    if labels and key in labels:
        return labels[key]
    return key


def _conditional_skill_ids(rules: dict[str, object]) -> list[UUID]:
    raw = rules.get("conditional")
    if not isinstance(raw, list):
        return []
    skill_ids: list[UUID] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        values = item.get("add_skill_ids")
        if not isinstance(values, list):
            continue
        for value in values:
            try:
                skill_ids.append(UUID(str(value)))
            except ValueError:
                continue
    return skill_ids


def _render_extra_skill_rules(
    rules: dict[str, object],
    skill_labels: dict[str, str] | None,
) -> list[str]:
    raw = rules.get("conditional")
    if not isinstance(raw, list) or not raw:
        return []
    lines: list[str] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        matcher = item.get("if")
        if not isinstance(matcher, dict):
            matcher = {}
        needles_raw = matcher.get("query_contains_any")
        needles = (
            [str(needle).strip() for needle in needles_raw if str(needle).strip()]
            if isinstance(needles_raw, list)
            else []
        )
        intent_raw = matcher.get("intent")
        intent = str(intent_raw).strip() if isinstance(intent_raw, str) else ""
        refs: list[str] = []
        for key in ("add_skill_ids", "add_skill_slugs"):
            values = item.get(key)
            if not isinstance(values, list):
                continue
            for value in values:
                label = _skill_label(value, skill_labels)
                if label:
                    refs.append(label)
        if not refs or (not needles and not intent):
            continue
        skill_text = ", ".join(f"`{ref}`" for ref in refs)
        if needles and intent:
            needle_text = " or ".join(f"`{needle}`" for needle in needles)
            lines.append(
                f"- If the query contains {needle_text} or the intent is "
                f"`{intent}`, add {skill_text}"
            )
        elif needles:
            needle_text = " or ".join(f"`{needle}`" for needle in needles)
            lines.append(f"- If the query contains {needle_text}, add {skill_text}")
        else:
            lines.append(f"- If the intent is `{intent}`, add {skill_text}")
    if not lines:
        return []
    return ["", "## Extra skills", ""] + lines


def render_playbook_section(
    rules: dict[str, object] | None,
    skill_labels: dict[str, str] | None = None,
) -> list[str]:
    """Render documented playbook keys for SCENARIO.md and the editor preview."""
    if not rules:
        return []
    lines: list[str] = []
    domain = rules.get("domain")
    if isinstance(domain, str) and domain.strip():
        lines.extend(["", "## Domain", "", domain.strip()])

    objective = rules.get("objective")
    if isinstance(objective, str) and objective.strip():
        lines.extend(["", "## Objective", "", objective.strip()])

    inputs = rules.get("required_inputs")
    if isinstance(inputs, list) and inputs:
        lines.extend(["", "## Required inputs", ""])
        lines.extend(f"- {item}" for item in inputs if str(item).strip())

    lines.extend(_render_extra_skill_rules(rules, skill_labels))

    phases = rules.get("phases")
    if isinstance(phases, list) and phases:
        lines.extend(["", "## Phases", ""])
        for phase in phases:
            if isinstance(phase, dict):
                phase_id = str(phase.get("id") or phase.get("name") or "phase")
                done = phase.get("done_when")
                line = f"- **{phase_id}**"
                if done:
                    line += f" — done when: {done}"
                lines.append(line)
            elif str(phase).strip():
                lines.append(f"- {phase}")

    deliverables = rules.get("deliverables")
    if isinstance(deliverables, list) and deliverables:
        lines.extend(["", "## Deliverables", ""])
        lines.extend(f"- `{item}`" for item in deliverables if str(item).strip())

    gates = rules.get("quality_gates")
    if isinstance(gates, list) and gates:
        lines.extend(["", "## Quality gates", ""])
        lines.extend(f"- {item}" for item in gates if str(item).strip())

    refusals = rules.get("refusal_rules")
    if isinstance(refusals, list) and refusals:
        lines.extend(["", "## Refusal rules", ""])
        lines.extend(f"- {item}" for item in refusals if str(item).strip())

    return lines


def render_report_template_section(template: ReportTemplate) -> list[str]:
    """Render the report-template instructions for SCENARIO.md.

    A markdown template contributes its outline. A Word template instead points
    the agent at the pushed asset and states the typed placeholder contract, so
    the agent fills the supplied document rather than inventing its own
    formatting.
    """
    lines: list[str] = []
    if template.description:
        lines.extend(["", template.description])

    if template.kind is not ReportTemplateKind.DOCX:
        if template.body:
            lines.extend(["", template.body.strip()])
        return lines

    asset_path = agent_template_path(template)
    lines.extend(
        [
            "",
            "### Report format: Word template (required)",
            "",
            f"Produce the report by filling `{asset_path}`. Keep its styles, "
            "headers and tables — do not rewrite the document from scratch and "
            "do not substitute a markdown report.",
            "",
            "The Word file is required even if the sandbox copy step failed. "
            "Do not fall back to a markdown report.",
            "",
            "```bash",
            f"cp {asset_path} outputs/report-template.docx",
            "# write outputs/report-data.json keyed by the placeholders below",
            "python .opencode/skills/docx/scripts/fill_template.py \\",
            "  --template outputs/report-template.docx \\",
            "  --data outputs/report-data.json \\",
            "  --output outputs/report.docx",
            "```",
        ]
    )
    schema = normalize_placeholder_schema(template.placeholders)
    if schema:
        lines.extend(
            [
                "",
                "Placeholders to fill (every required token must get a value; "
                "use an explicit `未获取` or `N/A` rather than leaving a token "
                "unfilled):",
                "",
            ]
        )
        for spec in schema:
            required = "required" if spec["required"] else "optional"
            line = f"- `{{{{{spec['name']}}}}}` ({spec['kind']}, {required})"
            if spec["description"]:
                line += f" — {spec['description']}"
            if spec["example"]:
                line += f" Example: {spec['example']}"
            lines.append(line)
        collections = table_collections(schema)
        if collections:
            lines.extend(
                [
                    "",
                    "Repeating tables use a prototype row. Supply an array of "
                    "objects. The filler clones the row once per item.",
                    "",
                    "```json",
                    "{",
                ]
            )
            example_parts: list[str] = []
            for collection, fields in collections.items():
                inner = ", ".join(f'"{field}": "…"' for field in fields)
                example_parts.append(f'  "{collection}": [{{{inner}}}]')
            lines.append(",\n".join(example_parts))
            lines.extend(["}", "```"])
    else:
        lines.extend(
            [
                "",
                "This template declares no placeholders — it is fixed content. "
                "Copy it and append your findings using the same styles.",
            ]
        )
    if template.body:
        lines.extend(["", "Section guidance:", "", template.body.strip()])
    return lines


def render_scenario_markdown_named(
    db_session: Session, scenario: Scenario, query: str | None = None
) -> str:
    rules = scenario.rules or {}
    skill_ids = resolve_scenario_skill_ids(scenario, query)
    label_ids = list(dict.fromkeys(skill_ids + _conditional_skill_ids(rules)))
    labels = skill_name_map(db_session, label_ids)
    names = [labels[str(skill_id)] for skill_id in skill_ids if str(skill_id) in labels]
    lines = _scenario_header(scenario.name, scenario.description or "")
    if names:
        lines.extend(f"- {name}" for name in names)
    else:
        lines.append("- (no skills bound)")
    lines.extend(render_playbook_section(rules, labels))
    if scenario.report_template:
        lines.extend(["", f"Preferred report template: `{scenario.report_template}`"])
        template = get_report_template_by_slug(db_session, scenario.report_template)
        if template is not None:
            lines.extend(render_report_template_section(template))
    return "\n".join(lines).strip() + "\n"


def merge_skill_id_strings(*groups: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for group in groups:
        for raw in group:
            text = raw.strip()
            if not text or text in seen:
                continue
            seen.add(text)
            ordered.append(text)
    return ordered


def apply_scenario_to_turn(
    db_session: Session,
    *,
    scenario_id: UUID,
    user: User,
    query: str,
    selected_skill_ids: list[str],
    sandbox_manager: _WorkspaceWriter | None = None,
    sandbox_id: UUID | None = None,
    session_id: UUID | None = None,
) -> list[str]:
    """Merge resolved scenario skills and rewrite SCENARIO.md for this prompt."""
    scenario = get_scenario_for_user(db_session, scenario_id, user)
    resolved = [str(skill_id) for skill_id in resolve_scenario_skill_ids(scenario, query)]
    merged = merge_skill_id_strings(resolved, selected_skill_ids)
    if (
        sandbox_manager is not None
        and sandbox_id is not None
        and session_id is not None
    ):
        try:
            content = render_scenario_markdown_named(db_session, scenario, query)
            sandbox_manager.write_sandbox_file(
                sandbox_id, f"sessions/{session_id}/SCENARIO.md", content
            )
        except Exception:
            logger.exception(
                "Failed to rewrite SCENARIO.md for session %s", session_id
            )
    return merged


def write_scenario_md_to_session(
    db_session: Session,
    sandbox_manager: SandboxManager,
    sandbox_id: UUID,
    session_id: UUID,
    scenario_id: UUID,
    user: User,
    query: str | None = None,
    *,
    push_template: bool = True,
) -> None:
    scenario = get_scenario_for_user(db_session, scenario_id, user)
    content = render_scenario_markdown_named(db_session, scenario, query)
    sandbox_manager.write_sandbox_file(
        sandbox_id, f"sessions/{session_id}/SCENARIO.md", content
    )
    if push_template:
        _push_scenario_report_template(db_session, sandbox_manager, sandbox_id, scenario)


def _push_scenario_report_template(
    db_session: Session,
    sandbox_manager: SandboxManager,
    sandbox_id: UUID,
    scenario: Scenario,
) -> None:
    """Ship the scenario's Word template, if it has one.

    Best-effort: SCENARIO.md is already written and already says the Word file
    is required, so a push failure must not silently fall back to markdown and
    must not fail session setup.
    """
    if not scenario.report_template:
        return
    template = get_report_template_by_slug(db_session, scenario.report_template)
    if template is None or template.kind is not ReportTemplateKind.DOCX:
        return
    try:
        push_report_templates_to_sandbox(sandbox_manager, sandbox_id, [template])
    except Exception:
        logger.warning(
            "Failed to push Word template '%s' to sandbox %s",
            template.slug,
            sandbox_id,
            exc_info=True,
        )
