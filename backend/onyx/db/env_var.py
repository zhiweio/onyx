"""Database operations for Craft environment variables / secrets.

Semantics follow GitHub Actions / GitLab CI:

- USER-scope rows are private to their creator.
- PROJECT-scope rows belong to a Craft project; writing them requires
  project write access, reading / granting them requires read access.
- Secret values are write-only: no function here returns a stored secret
  to an API caller. The only plaintext reader is the scheduled-task
  executor (``resolve_env_vars_for_task_run``), which re-validates grants
  at run time.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from onyx.db.craft_project import (
    list_projects_for_user,
    require_project_for_user,
    require_project_write_for_user,
)
from onyx.db.enums import EnvVarScope
from onyx.db.models import (
    CraftProject,
    EnvVar,
    ScheduledTask,
    ScheduledTaskEnvVar,
    User,
)
from onyx.error_handling.error_codes import OnyxErrorCode
from onyx.error_handling.exceptions import OnyxError
from onyx.utils.logger import setup_logger

logger = setup_logger()


# ---------------------------------------------------------------------------
# Validation rules
# ---------------------------------------------------------------------------

# Same character set GitHub Actions allows for variable / secret names.
ENV_VAR_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
ENV_VAR_MAX_NAME_LENGTH = 255
ENV_VAR_MAX_VALUE_LENGTH = 64_000
# Masked-secret floor (GitLab requires 8+ single-line characters); short
# values cannot be masked reliably and would leak in run transcripts.
SECRET_MIN_VALUE_LENGTH = 8
# Prefixes owned by the sandbox / proxy infrastructure. Blocking them keeps
# a future env-injection path from being shadowed by user-controlled rows.
ENV_VAR_RESERVED_PREFIXES = ("GH_", "GITHUB_", "ONYX_", "OPENCODE_", "SANDBOX_")


def validate_env_var_name(name: str) -> None:
    """Raise ``OnyxError(INVALID_INPUT)`` when the name is not usable."""
    if not name or len(name) > ENV_VAR_MAX_NAME_LENGTH:
        raise OnyxError(
            OnyxErrorCode.INVALID_INPUT,
            f"Name must be 1-{ENV_VAR_MAX_NAME_LENGTH} characters",
        )
    if not ENV_VAR_NAME_PATTERN.fullmatch(name):
        raise OnyxError(
            OnyxErrorCode.INVALID_INPUT,
            "Name must match [A-Za-z_][A-Za-z0-9_]*",
        )
    if name.upper().startswith(ENV_VAR_RESERVED_PREFIXES):
        raise OnyxError(
            OnyxErrorCode.INVALID_INPUT,
            f"Name must not start with one of {ENV_VAR_RESERVED_PREFIXES}",
        )


def validate_env_var_value(value: str, *, is_secret: bool) -> None:
    """Raise ``OnyxError(INVALID_INPUT)`` when the value is not usable."""
    if not value or len(value) > ENV_VAR_MAX_VALUE_LENGTH:
        raise OnyxError(
            OnyxErrorCode.INVALID_INPUT,
            f"Value must be 1-{ENV_VAR_MAX_VALUE_LENGTH} characters",
        )
    if is_secret:
        # Single line + minimum length keep run-time masking reliable.
        if len(value) < SECRET_MIN_VALUE_LENGTH:
            raise OnyxError(
                OnyxErrorCode.INVALID_INPUT,
                f"Secret values must be at least {SECRET_MIN_VALUE_LENGTH} characters",
            )
        if any(ch in value for ch in ("\n", "\r")):
            raise OnyxError(
                OnyxErrorCode.INVALID_INPUT,
                "Secret values must not contain newlines",
            )


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def create_env_var(
    *,
    db_session: Session,
    user: User,
    name: str,
    value: str,
    is_secret: bool,
    scope: EnvVarScope,
    project_id: UUID | None = None,
) -> EnvVar:
    """Insert an env var / secret row.

    PROJECT scope requires write access to the project (owner or group
    manager / curator); USER scope needs no extra authority.
    """
    validate_env_var_name(name)
    validate_env_var_value(value, is_secret=is_secret)

    if scope == EnvVarScope.PROJECT:
        if project_id is None:
            raise OnyxError(
                OnyxErrorCode.INVALID_INPUT,
                "project_id is required for project-scoped env vars",
            )
        require_project_write_for_user(db_session, project_id, user)
    else:
        project_id = None

    existing = _fetch_same_name(db_session, user_id=user.id, project_id=project_id, name=name)
    if existing is not None:
        raise OnyxError(
            OnyxErrorCode.INVALID_INPUT,
            f"An env var or secret named '{name}' already exists in this scope",
        )

    row = EnvVar(
        name=name,
        value=value,
        is_secret=is_secret,
        scope=scope,
        user_id=user.id,
        project_id=project_id,
    )
    db_session.add(row)
    db_session.flush()
    return row


def _fetch_same_name(
    db_session: Session, *, user_id: UUID, project_id: UUID | None, name: str
) -> EnvVar | None:
    """Fetch the row occupying ``name`` in one scope (user or project)."""
    stmt = select(EnvVar).where(EnvVar.name == name)
    if project_id is None:
        stmt = stmt.where(
            EnvVar.scope == EnvVarScope.USER, EnvVar.user_id == user_id
        )
    else:
        stmt = stmt.where(
            EnvVar.scope == EnvVarScope.PROJECT, EnvVar.project_id == project_id
        )
    return db_session.scalars(stmt.limit(1)).first()


def _require_env_var_for_user(
    db_session: Session, env_var_id: UUID, user: User
) -> EnvVar:
    """Fetch a row the user may manage, else raise.

    USER scope: the creator only. PROJECT scope: project write access.
    """
    row = db_session.get(EnvVar, env_var_id)
    if row is None:
        raise OnyxError(OnyxErrorCode.NOT_FOUND, "Env var not found")
    if row.scope == EnvVarScope.USER:
        if row.user_id != user.id:
            raise OnyxError(OnyxErrorCode.NOT_FOUND, "Env var not found")
    else:
        assert row.project_id is not None
        require_project_write_for_user(db_session, row.project_id, user)
    return row


def update_env_var(
    *,
    db_session: Session,
    user: User,
    env_var_id: UUID,
    name: str | None = None,
    value: str | None = None,
) -> EnvVar:
    """Rename and / or overwrite the value. Scope is immutable.

    Secret values are write-only: the caller cannot read the stored value,
    only replace it.
    """
    row = _require_env_var_for_user(db_session, env_var_id, user)

    if name is not None and name != row.name:
        validate_env_var_name(name)
        existing = _fetch_same_name(
            db_session,
            user_id=row.user_id,
            project_id=row.project_id,
            name=name,
        )
        if existing is not None and existing.id != row.id:
            raise OnyxError(
                OnyxErrorCode.INVALID_INPUT,
                f"An env var or secret named '{name}' already exists in this scope",
            )
        row.name = name

    if value is not None:
        validate_env_var_value(value, is_secret=row.is_secret)
        row.value = value

    db_session.flush()
    return row


def delete_env_var(*, db_session: Session, user: User, env_var_id: UUID) -> EnvVar:
    """Hard-delete a row. Cascades: every task grant on it is revoked."""
    row = _require_env_var_for_user(db_session, env_var_id, user)
    db_session.delete(row)
    db_session.flush()
    return row


# ---------------------------------------------------------------------------
# Listing (grant-time view)
# ---------------------------------------------------------------------------


def list_env_vars_for_user(*, db_session: Session, user: User) -> list[EnvVar]:
    """The caller's own USER-scope rows, most recently updated first."""
    return list(
        db_session.scalars(
            select(EnvVar)
            .where(EnvVar.scope == EnvVarScope.USER, EnvVar.user_id == user.id)
            .order_by(desc(EnvVar.updated_at))
        )
    )


def list_env_vars_for_project(
    *,
    db_session: Session,
    user: User,
    project_id: UUID,
) -> list[EnvVar]:
    """A project's rows; requires read access to the project."""
    require_project_for_user(db_session, project_id, user)
    return list(
        db_session.scalars(
            select(EnvVar)
            .where(
                EnvVar.scope == EnvVarScope.PROJECT, EnvVar.project_id == project_id
            )
            .order_by(desc(EnvVar.updated_at))
        )
    )


def list_grantable_env_vars(
    *,
    db_session: Session,
    user: User,
    project_id: UUID | None = None,
) -> list[tuple[EnvVar, CraftProject | None]]:
    """Rows the caller may grant to a task, with their project row.

    Returns the caller's USER-scope rows plus the rows of ``project_id``.
    ``project_id`` must be readable by the caller; ``None`` returns only
    USER-scope rows. Used by the task editor and the resolution-time
    re-validation below.
    """
    results: list[tuple[EnvVar, CraftProject | None]] = [
        (row, None) for row in list_env_vars_for_user(db_session=db_session, user=user)
    ]
    if project_id is None:
        return results
    project_rows = list_env_vars_for_project(
        db_session=db_session, user=user, project_id=project_id
    )
    project = db_session.get(CraftProject, project_id)
    results.extend((row, project) for row in project_rows)
    return results


def list_grantable_env_vars_across_projects(
    *,
    db_session: Session,
    user: User,
) -> list[tuple[EnvVar, CraftProject | None]]:
    """USER-scope rows plus the rows of every project the caller can read.

    One query pair for the management page; grouped by scope client-side.
    """
    results: list[tuple[EnvVar, CraftProject | None]] = [
        (row, None) for row in list_env_vars_for_user(db_session=db_session, user=user)
    ]
    projects = list_projects_for_user(db_session, user)
    if not projects:
        return results
    project_by_id = {project.id: project for project in projects}
    project_rows = db_session.scalars(
        select(EnvVar)
        .where(
            EnvVar.scope == EnvVarScope.PROJECT,
            EnvVar.project_id.in_(project_by_id.keys()),
        )
        .order_by(desc(EnvVar.updated_at))
    ).all()
    results.extend(
        (row, project_by_id[row.project_id])
        for row in project_rows
        if row.project_id in project_by_id
    )
    return results


def validate_task_env_var_grants(
    *,
    db_session: Session,
    user: User,
    project_id: UUID | None,
    env_var_ids: list[UUID],
    already_granted_ids: frozenset[UUID] = frozenset(),
) -> None:
    """Reject new ids the task owner cannot grant.

    Mirrors the MCP pre-approval tolerance model: ids already granted to
    the task may outlive their access; the executor re-validates at run
    time, and the editor shows them as stale. New ids must be grantable
    now: the owner's USER-scope rows or the rows of ``project_id``.
    Duplicate names across the two scopes are rejected — no silent
    precedence.
    """
    if not env_var_ids:
        return
    grantable = {
        row.id: row
        for row, _ in list_grantable_env_vars(
            db_session=db_session, user=user, project_id=project_id
        )
    }
    unknown = sorted(set(env_var_ids) - set(grantable) - already_granted_ids)
    if unknown:
        raise OnyxError(
            OnyxErrorCode.INVALID_INPUT,
            f"Unknown or unavailable env var id(s): {[str(u) for u in unknown]}",
        )
    names: dict[str, EnvVar] = {}
    for env_var_id in env_var_ids:
        row = grantable.get(env_var_id)
        if row is None:
            # Stale retained grant — the run-time re-validation decides it.
            continue
        if row.name in names:
            raise OnyxError(
                OnyxErrorCode.INVALID_INPUT,
                f"'{row.name}' is granted twice (user and project scope) — "
                "remove one of the duplicates",
            )
        names[row.name] = row


# ---------------------------------------------------------------------------
# Run-time resolution (executor)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResolvedEnvVars:
    """Plaintext values for one task run.

    ``values`` maps name -> decrypted value for every still-valid grant.
    ``secret_values`` holds only the secret plaintexts, for the run-time
    masker. Both must never be logged or serialized.
    """

    values: dict[str, str]
    secret_values: list[str]


def resolve_env_vars_for_task_run(
    *,
    db_session: Session,
    task: ScheduledTask,
) -> ResolvedEnvVars:
    """Resolve the task's grants into plaintext values, re-validating each.

    A grant survives only when the row still exists and still belongs to
    the task's scope: USER rows must be owned by the task owner; PROJECT
    rows must belong to the task's project. Stale grants (var deleted,
    task moved between projects) are skipped here and pruned on the next
    task edit — they are inert, matching the pre-approval model.
    """
    rows = db_session.scalars(
        select(EnvVar)
        .join(ScheduledTaskEnvVar, ScheduledTaskEnvVar.env_var_id == EnvVar.id)
        .where(ScheduledTaskEnvVar.scheduled_task_id == task.id)
    ).all()

    values: dict[str, str] = {}
    secret_values: list[str] = []
    for row in rows:
        if row.scope == EnvVarScope.USER:
            if row.user_id != task.user_id:
                continue
        elif row.project_id != task.project_id or task.project_id is None:
            continue
        values[row.name] = row.value.get_value(apply_mask=False)
        if row.is_secret:
            secret_values.append(values[row.name])
    return ResolvedEnvVars(values=values, secret_values=secret_values)
