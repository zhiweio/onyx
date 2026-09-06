from typing import Any
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from onyx.auth.permissions import has_global_permission
from onyx.db.enums import Permission, ScenarioAccessLevel, ScenarioSharePermission
from onyx.db.models import (
    Scenario,
    Scenario__Skill,
    Scenario__User,
    Scenario__UserGroup,
    User,
    User__UserGroup,
)
from onyx.error_handling.error_codes import OnyxErrorCode
from onyx.error_handling.exceptions import OnyxError

COPY_NAME_SUFFIX = " (copy)"
SCENARIO_NAME_MAX = 128


def copy_scenario_name(name: str) -> str:
    if len(name) + len(COPY_NAME_SUFFIX) <= SCENARIO_NAME_MAX:
        return f"{name}{COPY_NAME_SUFFIX}"
    return f"{name[: SCENARIO_NAME_MAX - len(COPY_NAME_SUFFIX)]}{COPY_NAME_SUFFIX}"


def is_workspace_scenario(scenario: Scenario) -> bool:
    return scenario.author_user_id is None


def _group_ids_for_user(db_session: Session, user_id: UUID) -> list[int]:
    return list(
        db_session.scalars(
            select(User__UserGroup.user_group_id).where(
                User__UserGroup.user_id == user_id
            )
        ).all()
    )


def scenario_visible_clause(user: User):
    group_ids = select(User__UserGroup.user_group_id).where(
        User__UserGroup.user_id == user.id
    )
    return or_(
        Scenario.author_user_id == user.id,
        Scenario.public_permission.is_not(None),
        Scenario.id.in_(
            select(Scenario__User.scenario_id).where(Scenario__User.user_id == user.id)
        ),
        Scenario.id.in_(
            select(Scenario__UserGroup.scenario_id).where(
                Scenario__UserGroup.user_group_id.in_(group_ids)
            )
        ),
    )


def access_level_for_scenario(
    db_session: Session, scenario: Scenario, user: User
) -> ScenarioAccessLevel | None:
    if scenario.author_user_id == user.id:
        return ScenarioAccessLevel.OWNER
    if is_workspace_scenario(scenario) and has_global_permission(
        user, Permission.FULL_ADMIN_PANEL_ACCESS
    ):
        return ScenarioAccessLevel.OWNER
    user_share = db_session.scalar(
        select(Scenario__User.permission).where(
            Scenario__User.scenario_id == scenario.id,
            Scenario__User.user_id == user.id,
        )
    )
    if user_share == ScenarioSharePermission.EDITOR:
        return ScenarioAccessLevel.EDITOR
    group_ids = _group_ids_for_user(db_session, user.id)
    if group_ids:
        group_share = db_session.scalar(
            select(Scenario__UserGroup.permission).where(
                Scenario__UserGroup.scenario_id == scenario.id,
                Scenario__UserGroup.user_group_id.in_(group_ids),
            )
        )
        if group_share == ScenarioSharePermission.EDITOR:
            return ScenarioAccessLevel.EDITOR
        if group_share == ScenarioSharePermission.VIEWER:
            return ScenarioAccessLevel.VIEWER
    if user_share == ScenarioSharePermission.VIEWER:
        return ScenarioAccessLevel.VIEWER
    if scenario.public_permission == ScenarioSharePermission.EDITOR:
        return ScenarioAccessLevel.EDITOR
    if scenario.public_permission == ScenarioSharePermission.VIEWER:
        return ScenarioAccessLevel.VIEWER
    return None


def require_scenario_access(
    db_session: Session,
    scenario: Scenario,
    user: User,
    *,
    editor: bool = False,
) -> ScenarioAccessLevel:
    level = access_level_for_scenario(db_session, scenario, user)
    if level is None:
        raise OnyxError(OnyxErrorCode.NOT_FOUND, "Scenario not found")
    if editor and level not in (ScenarioAccessLevel.OWNER, ScenarioAccessLevel.EDITOR):
        raise OnyxError(OnyxErrorCode.INSUFFICIENT_PERMISSIONS)
    return level


def list_scenarios_for_user(db_session: Session, user: User) -> list[Scenario]:
    stmt = (
        select(Scenario)
        .options(
            selectinload(Scenario.skill_links),
            selectinload(Scenario.user_shares),
            selectinload(Scenario.group_shares),
        )
        .where(scenario_visible_clause(user))
        .order_by(Scenario.updated_at.desc())
    )
    return list(db_session.scalars(stmt).unique().all())


def get_scenario_for_user(
    db_session: Session, scenario_id: UUID, user: User
) -> Scenario:
    scenario = db_session.scalar(
        select(Scenario)
        .options(
            selectinload(Scenario.skill_links),
            selectinload(Scenario.user_shares),
            selectinload(Scenario.group_shares),
        )
        .where(Scenario.id == scenario_id)
    )
    if scenario is None:
        raise OnyxError(OnyxErrorCode.NOT_FOUND, "Scenario not found")
    require_scenario_access(db_session, scenario, user)
    return scenario


def create_scenario(
    db_session: Session,
    *,
    user: User,
    name: str,
    description: str,
    rules: dict[str, Any],
    skill_ids: list[UUID],
    report_template: str | None,
) -> Scenario:
    scenario = Scenario(
        name=name,
        description=description,
        author_user_id=user.id,
        rules=rules,
        report_template=report_template,
    )
    db_session.add(scenario)
    db_session.flush()
    for i, skill_id in enumerate(skill_ids):
        db_session.add(
            Scenario__Skill(
                scenario_id=scenario.id, skill_id=skill_id, sort_order=i
            )
        )
    db_session.commit()
    db_session.refresh(scenario)
    return get_scenario_for_user(db_session, scenario.id, user)


def duplicate_scenario(
    db_session: Session, scenario: Scenario, user: User
) -> Scenario:
    skill_ids = [
        link.skill_id
        for link in sorted(scenario.skill_links, key=lambda row: row.sort_order)
    ]
    return create_scenario(
        db_session,
        user=user,
        name=copy_scenario_name(scenario.name),
        description=scenario.description,
        rules=dict(scenario.rules or {}),
        skill_ids=skill_ids,
        report_template=scenario.report_template,
    )


def update_scenario(
    db_session: Session,
    scenario: Scenario,
    *,
    name: str | None = None,
    description: str | None = None,
    rules: dict[str, Any] | None = None,
    skill_ids: list[UUID] | None = None,
    report_template: str | None = None,
) -> Scenario:
    if name is not None:
        scenario.name = name
    if description is not None:
        scenario.description = description
    if rules is not None:
        scenario.rules = rules
    if report_template is not None:
        scenario.report_template = report_template or None
    if skill_ids is not None:
        scenario.skill_links.clear()
        for i, skill_id in enumerate(skill_ids):
            scenario.skill_links.append(
                Scenario__Skill(
                    scenario_id=scenario.id, skill_id=skill_id, sort_order=i
                )
            )
    db_session.commit()
    db_session.refresh(scenario)
    return scenario


def delete_scenario(db_session: Session, scenario: Scenario) -> None:
    db_session.delete(scenario)
    db_session.commit()


def replace_scenario_shares(
    db_session: Session,
    scenario: Scenario,
    *,
    user_ids: list[UUID],
    group_ids: list[int],
    public_permission: ScenarioSharePermission | None,
) -> Scenario:
    scenario.user_shares.clear()
    scenario.group_shares.clear()
    for uid in user_ids:
        scenario.user_shares.append(
            Scenario__User(
                scenario_id=scenario.id,
                user_id=uid,
                permission=ScenarioSharePermission.VIEWER,
            )
        )
    for gid in group_ids:
        scenario.group_shares.append(
            Scenario__UserGroup(
                scenario_id=scenario.id,
                user_group_id=gid,
                permission=ScenarioSharePermission.VIEWER,
            )
        )
    scenario.public_permission = public_permission
    db_session.commit()
    db_session.refresh(scenario)
    return scenario


def resolve_scenario_skill_ids(
    scenario: Scenario, query: str | None = None
) -> list[UUID]:
    """Evaluate v1 rule JSON: always_skill_ids plus query_contains_any conditions."""
    rules = scenario.rules or {}
    ordered: list[UUID] = []
    seen: set[UUID] = set()

    def _add(raw_ids: list[Any]) -> None:
        for raw in raw_ids:
            try:
                skill_id = UUID(str(raw))
            except ValueError:
                continue
            if skill_id not in seen:
                seen.add(skill_id)
                ordered.append(skill_id)

    _add(list(rules.get("always_skill_ids") or []))
    for link in sorted(scenario.skill_links, key=lambda row: row.sort_order):
        if link.skill_id not in seen:
            seen.add(link.skill_id)
            ordered.append(link.skill_id)

    query_lower = (query or "").lower()
    for cond in rules.get("conditional") or []:
        if not isinstance(cond, dict):
            continue
        matcher = cond.get("if") or {}
        needles = matcher.get("query_contains_any") or []
        if needles and query_lower:
            if any(str(n).lower() in query_lower for n in needles):
                _add(list(cond.get("add_skill_ids") or []))
        intent = matcher.get("intent")
        if intent and query_lower and str(intent).lower() in query_lower:
            _add(list(cond.get("add_skill_ids") or []))
    return ordered
