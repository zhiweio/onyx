"""Scheduled tasks + env vars (executor half, ext-dep).

Extends ``test_scheduled_task_executor.py`` with the env-var contract:

* Granted values are substituted into the prompt handed to the sandbox
  agent, while the persisted transcript (turn 0) keeps the template and
  never sees the secret plaintext.
* A granted secret echoed by the agent is masked in persisted messages
  and in the run summary.
* A prompt reference with no valid grant fails the run fast with
  ``error_class=env_var_resolution_failed`` — before the sandbox is asked
  to do anything.
"""

from __future__ import annotations

import datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from acp.schema import AgentMessageChunk, PromptResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from onyx.db.enums import (
    EnvVarScope,
    SandboxStatus,
    ScheduledTaskErrorClass,
    ScheduledTaskRunStatus,
    ScheduledTaskStatus,
    ScheduledTaskTriggerSource,
)
from onyx.db.models import (
    EnvVar,
    ScheduledTask,
    ScheduledTaskEnvVar,
    ScheduledTaskRun,
    User,
)
from onyx.server.features.build.db.build_session import get_session_messages
from onyx.server.features.build.scheduled_tasks.executor import run_scheduled_task_logic
from onyx.server.features.build.session.manager import SessionManager
from tests.common.craft.stubs import StubSandboxManager

SECRET_VALUE = "sk-live-abcdef123456"


@pytest.fixture(autouse=True)
def _tenant_context(tenant_context: None) -> None:  # noqa: ARG001
    return None


def _seed_task_and_queued_run(
    db_session: Session,
    user: User,
    *,
    prompt: str,
    project_id: UUID | None = None,
    env_var_ids: list[UUID],
) -> ScheduledTaskRun:
    task = ScheduledTask(
        user_id=user.id,
        name="env-var-task",
        prompt=prompt,
        cron_expression="0 9 * * *",
        editor_mode="advanced",
        status=ScheduledTaskStatus.ACTIVE,
        next_run_at=datetime.datetime.now(datetime.timezone.utc)
        + datetime.timedelta(days=1),
        project_id=project_id,
    )
    db_session.add(task)
    db_session.flush()
    for env_var_id in env_var_ids:
        db_session.add(
            ScheduledTaskEnvVar(scheduled_task_id=task.id, env_var_id=env_var_id)
        )
    run = ScheduledTaskRun(
        task_id=task.id,
        status=ScheduledTaskRunStatus.QUEUED,
        trigger_source=ScheduledTaskTriggerSource.SCHEDULED,
        started_at=datetime.datetime.now(datetime.timezone.utc),
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)
    return run


def _seed_user_env_var(
    db_session: Session,
    user: User,
    *,
    name: str,
    value: str,
    is_secret: bool,
    project_id: UUID | None = None,
) -> EnvVar:
    row = EnvVar(
        name=name,
        value=value,
        is_secret=is_secret,
        scope=EnvVarScope.PROJECT if project_id is not None else EnvVarScope.USER,
        user_id=user.id,
        project_id=project_id,
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


def _prepare_stub(stub_sandbox_manager: StubSandboxManager) -> None:
    stub_sandbox_manager.health_check_returns = True
    stub_sandbox_manager.setup_session_workspace_silent = True
    stub_sandbox_manager.write_sandbox_file_silent = True
    stub_sandbox_manager.write_files_to_sandbox_silent = True


def _bypass_skill_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    # Bypass skill-payload: encrypted ExternalApp creds break local MIT decryption.
    monkeypatch.setattr(
        "onyx.server.features.build.session.sandbox_lifecycle.build_user_skills_payload",
        lambda *_: ("", {}),
    )


def test_granted_vars_substitute_into_prompt_and_mask_transcript(
    db_session: Session,
    test_user: User,
    sandbox: Any,  # noqa: ARG001
    session_manager_with_stub: SessionManager,  # noqa: ARG001
    stub_sandbox_manager: StubSandboxManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _bypass_skill_payload(monkeypatch)
    sandbox(user=test_user, status=SandboxStatus.RUNNING)

    secret = _seed_user_env_var(
        db_session, test_user, name="API_TOKEN", value=SECRET_VALUE, is_secret=True
    )
    city = _seed_user_env_var(
        db_session, test_user, name="CITY_CODE", value="310000", is_secret=False
    )
    prompt = "Fetch {{env.CITY_CODE}} data with token {{secrets.API_TOKEN}}."
    run = _seed_task_and_queued_run(
        db_session, test_user, prompt=prompt, env_var_ids=[secret.id, city.id]
    )

    # The agent echoes the secret in its reply — masking must catch it.
    stub_sandbox_manager.send_message_events = [
        AgentMessageChunk.model_validate(
            {
                "sessionUpdate": "agent_message_chunk",
                "content": {"type": "text", "text": f"Used {SECRET_VALUE} ok"},
            }
        ),
        PromptResponse.model_validate({"stopReason": "end_turn"}),
    ]
    _prepare_stub(stub_sandbox_manager)

    run_scheduled_task_logic(run.id)

    # 1. The sandbox received the rendered prompt.
    payload = stub_sandbox_manager.last_send_message_payload
    assert payload is not None
    assert SECRET_VALUE in payload["message"]
    assert "310000" in payload["message"]
    assert "{{secrets.API_TOKEN}}" not in payload["message"]

    # 2. The persisted turn 0 keeps the template, not the plaintext.
    session_id = payload.get("session_id") or _run_session_id(db_session, run.id)
    messages = get_session_messages(session_id=session_id, db_session=db_session)
    turn0 = messages[0].message_metadata
    assert isinstance(turn0, dict)
    content = turn0["content"]
    assert isinstance(content, dict)
    assert "{{secrets.API_TOKEN}}" in content["text"]
    assert SECRET_VALUE not in str(messages[0].message_metadata)

    # 3. Persisted agent output + run summary mask the secret.
    agent_text = str(messages[-1].message_metadata)
    assert "***" in agent_text
    assert SECRET_VALUE not in agent_text

    db_session.expire_all()
    refreshed = db_session.get(ScheduledTaskRun, run.id)
    assert refreshed is not None
    assert refreshed.status == ScheduledTaskRunStatus.SUCCEEDED
    assert refreshed.summary is not None
    assert SECRET_VALUE not in refreshed.summary
    assert "***" in refreshed.summary


def test_unresolved_reference_fails_run_before_sandbox_work(
    db_session: Session,
    test_user: User,
    sandbox: Any,  # noqa: ARG001
    session_manager_with_stub: SessionManager,  # noqa: ARG001
    stub_sandbox_manager: StubSandboxManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _bypass_skill_payload(monkeypatch)
    sandbox(user=test_user, status=SandboxStatus.RUNNING)

    # API_TOKEN exists but was never granted to the task.
    _seed_user_env_var(
        db_session, test_user, name="API_TOKEN", value=SECRET_VALUE, is_secret=True
    )
    run = _seed_task_and_queued_run(
        db_session,
        test_user,
        prompt="Fetch with {{secrets.API_TOKEN}}.",
        env_var_ids=[],
    )
    _prepare_stub(stub_sandbox_manager)

    run_scheduled_task_logic(run.id)

    db_session.expire_all()
    refreshed = db_session.get(ScheduledTaskRun, run.id)
    assert refreshed is not None
    assert refreshed.status == ScheduledTaskRunStatus.FAILED
    assert (
        refreshed.error_class == ScheduledTaskErrorClass.ENV_VAR_RESOLUTION_FAILED.value
    )
    assert "API_TOKEN" in (refreshed.error_detail or "")
    # Failed fast: the sandbox never received a message.
    assert stub_sandbox_manager.last_send_message_payload is None


def test_stale_project_grant_is_skipped_at_run_time(
    db_session: Session,
    test_user: User,
    sandbox: Any,  # noqa: ARG001
    session_manager_with_stub: SessionManager,  # noqa: ARG001
    stub_sandbox_manager: StubSandboxManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A project-scoped grant on a task with no project does not resolve —
    the executor treats the reference as unresolved and fails the run."""
    _bypass_skill_payload(monkeypatch)
    sandbox(user=test_user, status=SandboxStatus.RUNNING)

    from onyx.db.models import CraftProject

    project = CraftProject(
        user_id=test_user.id, name=f"stale-{uuid4().hex[:6]}", description=""
    )
    db_session.add(project)
    db_session.flush()
    stale_var = _seed_user_env_var(
        db_session,
        test_user,
        name="TAX_BASE",
        value="https://tax.example.com",
        is_secret=False,
        project_id=project.id,
    )
    # Task has NO project link, so the project-scoped grant is not grantable.
    run = _seed_task_and_queued_run(
        db_session,
        test_user,
        prompt="Fetch {{env.TAX_BASE}}.",
        env_var_ids=[stale_var.id],
    )
    _prepare_stub(stub_sandbox_manager)

    run_scheduled_task_logic(run.id)

    db_session.expire_all()
    refreshed = db_session.get(ScheduledTaskRun, run.id)
    assert refreshed is not None
    assert refreshed.status == ScheduledTaskRunStatus.FAILED
    assert (
        refreshed.error_class == ScheduledTaskErrorClass.ENV_VAR_RESOLUTION_FAILED.value
    )


def _run_session_id(db_session: Session, run_id: UUID) -> UUID:
    run = db_session.execute(
        select(ScheduledTaskRun).where(ScheduledTaskRun.id == run_id)
    ).scalar_one()
    assert run.session_id is not None
    return run.session_id
