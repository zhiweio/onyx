from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from onyx.auth.permissions import require_permission
from onyx.db.engine.sql_engine import get_session
from onyx.db.enums import Permission, ScenarioAccessLevel
from onyx.db.models import User
from onyx.db.scenario import (
    access_level_for_scenario,
    create_scenario,
    delete_scenario,
    duplicate_scenario,
    get_scenario_for_user,
    list_scenarios_for_user,
    replace_scenario_shares,
    require_scenario_access,
    resolve_scenario_skill_ids,
    update_scenario,
)
from onyx.server.features.scenario.models import (
    ScenarioListResponse,
    ScenarioPatchRequest,
    ScenarioResolveRequest,
    ScenarioResolveResponse,
    ScenarioResponse,
    ScenarioShareRequest,
    ScenarioSkillRef,
    ScenarioUpsertRequest,
)
from onyx.server.features.scenario.playbook import playbook_as_dict

router = APIRouter(prefix="/scenarios")


def _to_response(db_session: Session, scenario, user: User) -> ScenarioResponse:
    level = access_level_for_scenario(db_session, scenario, user)
    if level is None:
        level = ScenarioAccessLevel.VIEWER
    return ScenarioResponse(
        id=scenario.id,
        name=scenario.name,
        description=scenario.description,
        author_user_id=scenario.author_user_id,
        public_permission=scenario.public_permission,
        rules=scenario.rules or {},
        report_template=scenario.report_template,
        skill_ids=[link.skill_id for link in scenario.skill_links],
        skills=[
            ScenarioSkillRef(skill_id=link.skill_id, sort_order=link.sort_order)
            for link in scenario.skill_links
        ],
        access_level=level,
        shared_user_ids=[row.user_id for row in scenario.user_shares],
        shared_group_ids=[row.user_group_id for row in scenario.group_shares],
    )


@router.get("")
def list_scenarios(
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    db_session: Session = Depends(get_session),
) -> ScenarioListResponse:
    rows = list_scenarios_for_user(db_session, user)
    return ScenarioListResponse(
        scenarios=[_to_response(db_session, row, user) for row in rows]
    )


@router.post("")
def create_scenario_endpoint(
    request: ScenarioUpsertRequest,
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    db_session: Session = Depends(get_session),
) -> ScenarioResponse:
    scenario = create_scenario(
        db_session,
        user=user,
        name=request.name,
        description=request.description,
        rules=playbook_as_dict(request.rules),
        skill_ids=request.skill_ids,
        report_template=request.report_template,
    )
    return _to_response(db_session, scenario, user)


@router.get("/{scenario_id}")
def get_scenario_endpoint(
    scenario_id: UUID,
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    db_session: Session = Depends(get_session),
) -> ScenarioResponse:
    scenario = get_scenario_for_user(db_session, scenario_id, user)
    return _to_response(db_session, scenario, user)


@router.post("/{scenario_id}/duplicate")
def duplicate_scenario_endpoint(
    scenario_id: UUID,
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    db_session: Session = Depends(get_session),
) -> ScenarioResponse:
    scenario = get_scenario_for_user(db_session, scenario_id, user)
    copied = duplicate_scenario(db_session, scenario, user)
    return _to_response(db_session, copied, user)


@router.patch("/{scenario_id}")
def patch_scenario_endpoint(
    scenario_id: UUID,
    request: ScenarioPatchRequest,
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    db_session: Session = Depends(get_session),
) -> ScenarioResponse:
    scenario = get_scenario_for_user(db_session, scenario_id, user)
    require_scenario_access(db_session, scenario, user, editor=True)
    scenario = update_scenario(
        db_session,
        scenario,
        name=request.name,
        description=request.description,
        rules=playbook_as_dict(request.rules) if request.rules is not None else None,
        skill_ids=request.skill_ids,
        report_template=request.report_template,
    )
    return _to_response(db_session, scenario, user)


@router.delete("/{scenario_id}")
def delete_scenario_endpoint(
    scenario_id: UUID,
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    db_session: Session = Depends(get_session),
) -> None:
    scenario = get_scenario_for_user(db_session, scenario_id, user)
    require_scenario_access(db_session, scenario, user, editor=True)
    delete_scenario(db_session, scenario)


@router.patch("/{scenario_id}/share")
def share_scenario_endpoint(
    scenario_id: UUID,
    request: ScenarioShareRequest,
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    db_session: Session = Depends(get_session),
) -> ScenarioResponse:
    scenario = get_scenario_for_user(db_session, scenario_id, user)
    require_scenario_access(db_session, scenario, user, editor=True)
    scenario = replace_scenario_shares(
        db_session,
        scenario,
        user_ids=request.user_ids,
        group_ids=request.group_ids,
        public_permission=request.public_permission,
    )
    return _to_response(db_session, scenario, user)


@router.post("/{scenario_id}/resolve")
def resolve_scenario_endpoint(
    scenario_id: UUID,
    request: ScenarioResolveRequest,
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    db_session: Session = Depends(get_session),
) -> ScenarioResolveResponse:
    scenario = get_scenario_for_user(db_session, scenario_id, user)
    return ScenarioResolveResponse(
        scenario_id=scenario.id,
        skill_ids=resolve_scenario_skill_ids(scenario, request.query),
    )
