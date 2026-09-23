"""Env vars / secrets API + task grant wiring (HTTP contract)."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import delete

from onyx.db.engine.sql_engine import SqlEngine, get_session_with_current_tenant
from onyx.db.enums import ScheduledTaskStatus
from onyx.db.models import (
    CraftProject,
    EnvVar,
    ScheduledTask,
    ScheduledTaskEnvVar,
)
from shared_configs.configs import POSTGRES_DEFAULT_SCHEMA_STANDARD_VALUE
from shared_configs.contextvars import CURRENT_TENANT_ID_CONTEXTVAR
from tests.integration.common_utils.constants import API_SERVER_URL
from tests.integration.common_utils.http_client import client
from tests.integration.common_utils.managers.user import UserManager
from tests.integration.common_utils.test_models import DATestUser

_CREATED_ENV_VAR_IDS: list[UUID] = []
_CREATED_TASK_IDS: list[UUID] = []
_CREATED_PROJECT_IDS: list[UUID] = []


@pytest.fixture(autouse=True)
def _db_access() -> Generator[None, None, None]:
    SqlEngine.init_engine(pool_size=10, max_overflow=5)
    token = CURRENT_TENANT_ID_CONTEXTVAR.set(POSTGRES_DEFAULT_SCHEMA_STANDARD_VALUE)
    try:
        yield
    finally:
        CURRENT_TENANT_ID_CONTEXTVAR.reset(token)


@pytest.fixture(autouse=True)
def _cleanup(_db_access: None) -> Generator[None, None, None]:
    """Hard-delete rows this module created.

    Tasks are soft-deleted first so the live beat cannot fire them; env vars
    are hard-deleted so name-uniqueness doesn't collide across reruns.
    """
    _CREATED_ENV_VAR_IDS.clear()
    _CREATED_TASK_IDS.clear()
    _CREATED_PROJECT_IDS.clear()
    yield
    with get_session_with_current_tenant() as db_session:
        db_session.execute(
            delete(ScheduledTaskEnvVar).where(
                ScheduledTaskEnvVar.scheduled_task_id.in_(_CREATED_TASK_IDS)
            )
        )
        for task_id in _CREATED_TASK_IDS:
            task = db_session.get(ScheduledTask, task_id)
            if task is not None:
                task.deleted = True
                task.next_run_at = None
        db_session.execute(
            delete(EnvVar).where(EnvVar.id.in_(_CREATED_ENV_VAR_IDS))
        )
        db_session.execute(
            delete(CraftProject).where(CraftProject.id.in_(_CREATED_PROJECT_IDS))
        )
        db_session.commit()


def _url(*parts: str) -> str:
    base = f"{API_SERVER_URL}/build/env-vars"
    if not parts:
        return base
    return base + "/" + "/".join(parts)


def _create_env_var(
    user: DATestUser,
    *,
    name: str,
    value: str,
    is_secret: bool = False,
    project_id: UUID | None = None,
) -> httpx.Response:
    body: dict[str, Any] = {
        "name": name,
        "value": value,
        "is_secret": is_secret,
        "scope": "PROJECT" if project_id is not None else "USER",
    }
    if project_id is not None:
        body["project_id"] = str(project_id)
    response = client.post(
        _url(),
        json=body,
        headers=user.headers,
        cookies=user.cookies,
    )
    if response.is_success:
        env_var_id = response.json().get("id")
        if env_var_id:
            _CREATED_ENV_VAR_IDS.append(UUID(env_var_id))
    return response


def _create_project(user: DATestUser, name: str) -> dict[str, Any]:
    response = client.post(
        f"{API_SERVER_URL}/craft-projects",
        json={"name": name, "description": "", "instructions": None},
        headers=user.headers,
        cookies=user.cookies,
    )
    response.raise_for_status()
    project = response.json()
    _CREATED_PROJECT_IDS.append(UUID(project["id"]))
    return project


def _create_task(
    user: DATestUser,
    *,
    prompt: str = "Run the daily check.",
    project_id: UUID | None = None,
    env_var_ids: list[UUID] | None = None,
) -> httpx.Response:
    body: dict[str, Any] = {
        "name": f"task-{uuid4().hex[:8]}",
        "prompt": prompt,
        "editor_mode": "interval",
        "editor_payload": {"unit": "hours", "every": 1},
        "status": ScheduledTaskStatus.PAUSED.value,
    }
    if project_id is not None:
        body["project_id"] = str(project_id)
    if env_var_ids is not None:
        body["env_var_ids"] = [str(env_var_id) for env_var_id in env_var_ids]
    response = client.post(
        f"{API_SERVER_URL}/build/scheduled-tasks",
        json=body,
        headers=user.headers,
        cookies=user.cookies,
    )
    if response.is_success:
        task_id = response.json().get("id")
        if task_id:
            _CREATED_TASK_IDS.append(UUID(task_id))
    return response


# ---------------------------------------------------------------------------
# CRUD + permission matrix
# ---------------------------------------------------------------------------


def test_user_scope_crud_and_secret_write_only(admin_user: DATestUser) -> None:
    created = _create_env_var(
        admin_user, name=f"API_TOKEN_{uuid4().hex[:6]}", value="sk-1234567890", is_secret=True
    )
    created.raise_for_status()
    body = created.json()
    assert body["is_secret"] is True
    assert body["scope"] == "USER"
    assert body["value"] is None  # write-only: never echoed
    assert body["manageable"] is True

    env_var_id = body["id"]

    listed = client.get(
        _url(),
        headers=admin_user.headers,
        cookies=admin_user.cookies,
    )
    listed.raise_for_status()
    row = next(
        item for item in listed.json()["items"] if item["id"] == env_var_id
    )
    assert row["value"] is None

    # Overwrite the secret; the new value still never comes back.
    updated = client.patch(
        _url(env_var_id),
        json={"value": "sk-9876543210"},
        headers=admin_user.headers,
        cookies=admin_user.cookies,
    )
    updated.raise_for_status()
    assert updated.json()["value"] is None

    deleted = client.delete(
        _url(env_var_id),
        headers=admin_user.headers,
        cookies=admin_user.cookies,
    )
    assert deleted.status_code == 204
    _CREATED_ENV_VAR_IDS.remove(UUID(env_var_id))


def test_plain_variable_value_is_readable(admin_user: DATestUser) -> None:
    name = f"CITY_{uuid4().hex[:6]}"
    created = _create_env_var(admin_user, name=name, value="310000")
    created.raise_for_status()
    assert created.json()["value"] == "310000"
    assert created.json()["is_secret"] is False


def test_name_rules_reject_reserved_prefix_and_duplicates(admin_user: DATestUser) -> None:
    reserved = _create_env_var(admin_user, name="ONYX_TOKEN", value="abcdefgh")
    assert reserved.status_code == 400

    bad_chars = _create_env_var(admin_user, name="has space", value="abcdefgh")
    assert bad_chars.status_code == 400

    short_secret = _create_env_var(
        admin_user, name=f"S_{uuid4().hex[:6]}", value="short", is_secret=True
    )
    assert short_secret.status_code == 400

    name = f"DUP_{uuid4().hex[:6]}"
    first = _create_env_var(admin_user, name=name, value="aaaaaaaa")
    first.raise_for_status()
    duplicate = _create_env_var(admin_user, name=name, value="bbbbbbbb")
    assert duplicate.status_code == 400


def test_user_isolation_other_user_cannot_manage_or_see(
    admin_user: DATestUser,
) -> None:
    other = UserManager.create(name=f"envvar_other_{uuid4().hex[:6]}")

    created = _create_env_var(
        admin_user, name=f"PRIV_{uuid4().hex[:6]}", value="sk-1234567890", is_secret=True
    )
    created.raise_for_status()
    env_var_id = created.json()["id"]

    # Not listed for the other user.
    listed = client.get(_url(), headers=other.headers, cookies=other.cookies)
    listed.raise_for_status()
    assert all(item["id"] != env_var_id for item in listed.json()["items"])

    # Patch / delete by a non-owner 404s (existence is not leaked).
    patched = client.patch(
        _url(env_var_id),
        json={"value": "sk-0000000000"},
        headers=other.headers,
        cookies=other.cookies,
    )
    assert patched.status_code == 404
    deleted = client.delete(
        _url(env_var_id),
        headers=other.headers,
        cookies=other.cookies,
    )
    assert deleted.status_code == 404


def test_project_scope_requires_read_to_list_and_write_to_manage(
    admin_user: DATestUser,
) -> None:
    other = UserManager.create(name=f"envvar_proj_{uuid4().hex[:6]}")
    project = _create_project(admin_user, f"Shared {uuid4().hex[:6]}")

    # Another user without access cannot even see the project's vars.
    unlisted = client.get(
        _url(),
        params={"project_id": project["id"]},
        headers=other.headers,
        cookies=other.cookies,
    )
    assert unlisted.status_code == 404

    # Only project write access (owner here) may create project vars.
    created = _create_env_var(
        admin_user,
        name=f"TAX_BASE_{uuid4().hex[:6]}",
        value="https://tax.example.com",
        project_id=UUID(project["id"]),
    )
    created.raise_for_status()
    assert created.json()["scope"] == "PROJECT"
    assert created.json()["project_name"].startswith("Shared ")


# ---------------------------------------------------------------------------
# Task grant wiring
# ---------------------------------------------------------------------------


def test_task_grants_only_own_and_project_vars(admin_user: DATestUser) -> None:
    other = UserManager.create(name=f"envvar_grant_{uuid4().hex[:6]}")
    project = _create_project(admin_user, f"Grant {uuid4().hex[:6]}")

    own_var = _create_env_var(
        admin_user, name=f"OWN_{uuid4().hex[:6]}", value="value-own"
    )
    own_var.raise_for_status()
    project_var = _create_env_var(
        admin_user,
        name=f"PROJ_{uuid4().hex[:6]}",
        value="value-proj",
        project_id=UUID(project["id"]),
    )
    project_var.raise_for_status()
    other_var = _create_env_var(
        other, name=f"OTHER_{uuid4().hex[:6]}", value="value-other"
    )
    other_var.raise_for_status()

    own_id = own_var.json()["id"]
    project_id = UUID(project["id"])
    project_var_id = project_var.json()["id"]
    other_var_id = other_var.json()["id"]

    # Granting another user's var is rejected.
    rejected = _create_task(admin_user, env_var_ids=[UUID(other_var_id)])
    assert rejected.status_code == 400

    # A project var is grantable only when the task belongs to that project.
    no_project = _create_task(admin_user, env_var_ids=[UUID(project_var_id)])
    assert no_project.status_code == 400

    ok = _create_task(
        admin_user,
        project_id=project_id,
        env_var_ids=[UUID(own_id), UUID(project_var_id)],
    )
    ok.raise_for_status()
    detail = ok.json()
    assert detail["project_id"] == project["id"]
    assert sorted(detail["env_var_ids"]) == sorted([own_id, project_var_id])


def test_duplicate_name_across_scopes_rejected(admin_user: DATestUser) -> None:
    project = _create_project(admin_user, f"Dup {uuid4().hex[:6]}")
    name = f"DUPSCOPE_{uuid4().hex[:6]}"

    own = _create_env_var(admin_user, name=name, value="aaaaaaaa")
    own.raise_for_status()
    proj = _create_env_var(
        admin_user, name=name, value="bbbbbbbb", project_id=UUID(project["id"])
    )
    proj.raise_for_status()

    task = _create_task(
        admin_user,
        project_id=UUID(project["id"]),
        env_var_ids=[UUID(own.json()["id"]), UUID(proj.json()["id"])],
    )
    assert task.status_code == 400
    assert "twice" in task.text


def test_moving_task_to_another_project_prunes_grants(admin_user: DATestUser) -> None:
    project_a = _create_project(admin_user, f"PruneA {uuid4().hex[:6]}")
    project_b = _create_project(admin_user, f"PruneB {uuid4().hex[:6]}")
    var_a = _create_env_var(
        admin_user,
        name=f"PRUNEA_{uuid4().hex[:6]}",
        value="value-a",
        project_id=UUID(project_a["id"]),
    )
    var_a.raise_for_status()
    var_a_id = var_a.json()["id"]

    created = _create_task(
        admin_user,
        project_id=UUID(project_a["id"]),
        env_var_ids=[UUID(var_a_id)],
    )
    created.raise_for_status()
    task_id = created.json()["id"]

    moved = client.patch(
        f"{API_SERVER_URL}/build/scheduled-tasks/{task_id}",
        json={"project_id": project_b["id"]},
        headers=admin_user.headers,
        cookies=admin_user.cookies,
    )
    moved.raise_for_status()
    assert moved.json()["env_var_ids"] == []

    # Clearing the project link is an explicit null.
    cleared = client.patch(
        f"{API_SERVER_URL}/build/scheduled-tasks/{task_id}",
        json={"project_id": None},
        headers=admin_user.headers,
        cookies=admin_user.cookies,
    )
    cleared.raise_for_status()
    assert cleared.json()["project_id"] is None


def test_deleting_var_revokes_task_grant(admin_user: DATestUser) -> None:
    var = _create_env_var(admin_user, name=f"REVOKE_{uuid4().hex[:6]}", value="value-x")
    var.raise_for_status()
    var_id = var.json()["id"]

    created = _create_task(admin_user, env_var_ids=[UUID(var_id)])
    created.raise_for_status()
    task_id = created.json()["id"]
    assert created.json()["env_var_ids"] == [var_id]

    deleted = client.delete(
        _url(var_id),
        headers=admin_user.headers,
        cookies=admin_user.cookies,
    )
    assert deleted.status_code == 204
    _CREATED_ENV_VAR_IDS.remove(UUID(var_id))

    detail = client.get(
        f"{API_SERVER_URL}/build/scheduled-tasks/{task_id}",
        headers=admin_user.headers,
        cookies=admin_user.cookies,
    )
    detail.raise_for_status()
    assert detail.json()["env_var_ids"] == []
