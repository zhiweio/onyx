"""FastAPI router for Craft env vars / secrets.

Thin HTTP layer over ``onyx.db.env_var``. Mounted under the ``/build``
prefix (see ``backend/onyx/server/features/build/api.py``), which provides
the ``require_onyx_craft_enabled`` gate. Permission enforcement lives in
the DB ops: USER-scope rows are owner-only; PROJECT-scope rows require
project write access to manage and read access to list / grant.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from onyx.auth.permissions import require_permission
from onyx.db.craft_project import user_can_write_project
from onyx.db.engine.sql_engine import get_session
from onyx.db.enums import EnvVarScope, Permission
from onyx.db.env_var import (
    create_env_var,
    delete_env_var,
    list_grantable_env_vars,
    list_grantable_env_vars_across_projects,
    update_env_var,
)
from onyx.db.models import EnvVar, User
from onyx.server.features.build.env_vars.models import (
    EnvVarListResponse,
    EnvVarPatchRequest,
    EnvVarResponse,
    EnvVarUpsertRequest,
)
from onyx.utils.audit import (
    AuditAction,
    AuditOutcome,
    actor_from_user,
    emit_audit_event,
)
from onyx.utils.logger import setup_logger

logger = setup_logger()


router = APIRouter(prefix="/env-vars")


def _audit(
    action: AuditAction,
    user: User,
    env_var_id: UUID,
    *,
    scope: EnvVarScope,
    name: str,
    is_secret: bool,
    project_id: UUID | None,
) -> None:
    """Best-effort audit line. Never includes the value."""
    emit_audit_event(
        action,
        AuditOutcome.SUCCESS,
        actor=actor_from_user(user),
        resource_type="env_var",
        resource_id=str(env_var_id),
        extra={
            "scope": scope.value,
            "name": name,
            "is_secret": is_secret,
            "project_id": str(project_id) if project_id is not None else None,
        },
    )


@router.get("")
def list_env_vars_endpoint(
    project_id: UUID | None = Query(default=None),
    all_projects: bool = Query(default=False),
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    db_session: Session = Depends(get_session),
) -> EnvVarListResponse:
    """Rows the caller may grant to a task.

    Three modes: default returns the caller's USER-scope rows only;
    ``project_id`` adds that project's rows (must be readable);
    ``all_projects`` adds the rows of every readable project (management
    page). Secret values are always omitted.
    """
    if all_projects:
        rows = list_grantable_env_vars_across_projects(
            db_session=db_session, user=user
        )
    else:
        rows = list_grantable_env_vars(
            db_session=db_session, user=user, project_id=project_id
        )
    return EnvVarListResponse(
        items=[
            EnvVarResponse.from_model(
                row,
                project.name if project else None,
                manageable=_manageable(db_session, user, row),
            )
            for row, project in rows
        ]
    )


def _manageable(db_session: Session, user: User, row: EnvVar) -> bool:
    """Whether the caller may edit / delete the row (drives the UI)."""
    if row.scope == EnvVarScope.USER:
        return row.user_id == user.id
    if row.project_id is None:
        return False
    project = row.project
    if project is None:
        return False
    return user_can_write_project(db_session, project, user)


@router.post("")
def create_env_var_endpoint(
    request: EnvVarUpsertRequest,
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    db_session: Session = Depends(get_session),
) -> EnvVarResponse:
    row = create_env_var(
        db_session=db_session,
        user=user,
        name=request.name,
        value=request.value,
        is_secret=request.is_secret,
        scope=request.scope,
        project_id=request.project_id,
    )
    db_session.commit()
    db_session.refresh(row)
    _audit(
        AuditAction.ENV_VAR_CREATE,
        user,
        row.id,
        scope=row.scope,
        name=row.name,
        is_secret=row.is_secret,
        project_id=row.project_id,
    )
    project_name = row.project.name if row.project is not None else None
    return EnvVarResponse.from_model(
        row, project_name, manageable=_manageable(db_session, user, row)
    )


@router.patch("/{env_var_id}")
def update_env_var_endpoint(
    env_var_id: UUID,
    request: EnvVarPatchRequest,
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    db_session: Session = Depends(get_session),
) -> EnvVarResponse:
    row = update_env_var(
        db_session=db_session,
        user=user,
        env_var_id=env_var_id,
        name=request.name,
        value=request.value,
    )
    db_session.commit()
    db_session.refresh(row)
    _audit(
        AuditAction.ENV_VAR_UPDATE,
        user,
        row.id,
        scope=row.scope,
        name=row.name,
        is_secret=row.is_secret,
        project_id=row.project_id,
    )
    project_name = row.project.name if row.project is not None else None
    return EnvVarResponse.from_model(
        row, project_name, manageable=_manageable(db_session, user, row)
    )


@router.delete("/{env_var_id}")
def delete_env_var_endpoint(
    env_var_id: UUID,
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    db_session: Session = Depends(get_session),
) -> Response:
    row = delete_env_var(db_session=db_session, user=user, env_var_id=env_var_id)
    _audit(
        AuditAction.ENV_VAR_DELETE,
        user,
        row.id,
        scope=row.scope,
        name=row.name,
        is_secret=row.is_secret,
        project_id=row.project_id,
    )
    db_session.commit()
    return Response(status_code=204)
