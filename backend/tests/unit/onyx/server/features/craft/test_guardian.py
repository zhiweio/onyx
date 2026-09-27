"""Auto-review guardian: decisions, guardrails, shadow mode, circuit breaker."""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from onyx.db.enums import (
    ApprovalDecision,
)
from onyx.db.models import ActionApproval
from onyx.server.features.build.approvals import guardian


class _FakeDB:
    """Just enough Session for the guardian's queries.

    execute → the RUNNING-run lookup; scalar → the recent-quarantine check
    (None = clean); scalars → guardian rejection ids (circuit breaker);
    get → the task row.
    """

    def __init__(
        self,
        *,
        run_task_id: object = None,
        task: object = None,
        quarantine_id: object = None,
        reject_ids: tuple = (),
    ) -> None:
        self.run_task_id = run_task_id
        self.task = task
        self.quarantine_id = quarantine_id
        self.reject_ids = reject_ids
        self.commits = 0

    def execute(self, _stmt: object):  # noqa: ARG002
        task_id = self.run_task_id
        return SimpleNamespace(first=lambda: None if task_id is None else (task_id,))

    def scalar(self, _stmt: object):  # noqa: ARG002
        return self.quarantine_id

    def scalars(self, _stmt: object):  # noqa: ARG002
        return iter(self.reject_ids)

    def get(self, _model: type, task_id: object):  # noqa: ARG002
        return self.task

    def commit(self) -> None:
        self.commits += 1


def _approval() -> SimpleNamespace:
    return SimpleNamespace(
        approval_id=uuid4(),
        session_id=uuid4(),
        app_name="Slack",
        decision=None,
        payload={},
        actions=[{"action_type": "slack.chat.post", "policy": "ASK"}],
    )


def _task() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        user_id=uuid4(),
        name="Digest",
        prompt="Post the weekly digest to Slack.",
        reviewer_mode="auto_review",
        pre_approved_targets=[],
    )


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(guardian, "CRAFT_GUARDIAN_ENABLED", True)
    monkeypatch.setattr(guardian, "CRAFT_GUARDIAN_TIMEOUT_SECONDS", 5)
    monkeypatch.setattr(guardian, "CRAFT_GUARDIAN_REJECT_CIRCUIT_BREAKER", 2)
    monkeypatch.setattr(guardian, "CRAFT_GUARDIAN_QUARANTINE_ESCALATION_HOURS", 1)
    monkeypatch.setattr(guardian, "create_notification", lambda **_k: None)
    monkeypatch.setattr(guardian.approval_cache, "send_wake", lambda *_a, **_k: None)


def _llm_returning(content: str) -> object:
    class _R:
        choice = SimpleNamespace(message=SimpleNamespace(content=content))

    class _LLM:
        def invoke(self, *_a, **_k):
            return _R()

    return _LLM()


def test_auto_review_approves_and_records(monkeypatch) -> None:
    task = _task()
    db = _FakeDB(run_task_id=task.id, task=task)
    row = _approval()
    monkeypatch.setattr(
        guardian,
        "get_default_llm",
        lambda **_k: _llm_returning(
            '{"decision": "approve", "reason": "routine post", "risk": "low"}'
        ),
    )
    decided: list = []
    monkeypatch.setattr(
        guardian.action_approval_db,
        "try_record_decision",
        lambda db, *, approval_id, decision, decided_via: (  # noqa: ARG005
            decided.append((approval_id, decision)) or row
        ),
    )

    guardian._review_one(cast(Session, db), cast(ActionApproval, row))

    assert [d for _i, d in decided] == [ApprovalDecision.APPROVED]
    assert row.payload["guardian"]["effective"] is True
    assert row.payload["guardian"]["decision"] == "approve"


def test_shadow_mode_never_records(monkeypatch) -> None:
    task = _task()
    db = _FakeDB(run_task_id=task.id, task=task)
    row = _approval()
    monkeypatch.setattr(
        guardian,
        "get_default_llm",
        lambda **_k: _llm_returning(
            '{"decision": "approve", "reason": "routine", "risk": "low"}'
        ),
    )
    recorded: list = []
    monkeypatch.setattr(
        guardian.action_approval_db,
        "try_record_decision",
        lambda db, **_k: recorded.append(1) or row,  # noqa: ARG005
    )

    task.reviewer_mode = "auto_review_shadow"
    guardian._review_one(cast(Session, db), cast(ActionApproval, row))

    assert recorded == []
    assert row.payload["guardian"]["effective"] is False


def test_quarantined_session_escalates(monkeypatch) -> None:
    task = _task()
    db = _FakeDB(run_task_id=task.id, task=task, quarantine_id=uuid4())
    row = _approval()
    monkeypatch.setattr(
        guardian,
        "get_default_llm",
        lambda **_k: _llm_returning('{"decision": "approve"}'),
    )
    recorded: list = []
    monkeypatch.setattr(
        guardian.action_approval_db,
        "try_record_decision",
        lambda db, **_k: recorded.append(1) or row,  # noqa: ARG005
    )

    guardian._review_one(cast(Session, db), cast(ActionApproval, row))

    assert recorded == []
    assert row.payload["guardian"]["decision"] == "escalate"


def test_rejection_circuit_breaker_escalates(monkeypatch) -> None:
    task = _task()
    db = _FakeDB(
        run_task_id=task.id,
        task=task,
        reject_ids=(uuid4(), uuid4()),  # breaker threshold is 2
    )
    row = _approval()
    monkeypatch.setattr(
        guardian,
        "get_default_llm",
        lambda **_k: _llm_returning(
            '{"decision": "approve", "reason": "fine", "risk": "low"}'
        ),
    )
    recorded: list = []
    monkeypatch.setattr(
        guardian.action_approval_db,
        "try_record_decision",
        lambda db, **_k: recorded.append(1) or row,  # noqa: ARG005
    )

    guardian._review_one(cast(Session, db), cast(ActionApproval, row))

    assert recorded == []
    assert row.payload["guardian"]["decision"] == "escalate"


def test_llm_failure_escalates(monkeypatch) -> None:
    task = _task()
    row = _approval()
    db = _FakeDB(run_task_id=task.id, task=task)
    recorded: list = []
    monkeypatch.setattr(guardian, "get_default_llm", lambda **_k: _boom())
    monkeypatch.setattr(
        guardian.action_approval_db,
        "try_record_decision",
        lambda db, **_k: recorded.append(1) or row,  # noqa: ARG005
    )

    def _boom(*_a, **_k):
        raise RuntimeError("timeout")

    guardian._review_one(cast(Session, db), cast(ActionApproval, row))

    assert recorded == []
    assert row.payload["guardian"]["decision"] == "escalate"


def test_guardian_rejects_do_not_count_toward_graduation() -> None:
    """Structural guard: the guardian module must never wire graduation's
    decision recorder — only the user decision endpoint does."""
    import inspect

    src = inspect.getsource(guardian)
    assert "record_decision_outcome" not in src


def test_drain_disabled_returns_zero(monkeypatch) -> None:
    monkeypatch.setattr(guardian, "CRAFT_GUARDIAN_ENABLED", False)
    assert (
        guardian.drain_guardian_reviews(cast(Session, _FakeDB(run_task_id=None))) == 0
    )


def test_drain_reviews_pending_rows(monkeypatch) -> None:
    row = _approval()
    monkeypatch.setattr(
        guardian,
        "_pending_guardian_approvals",
        lambda _db: [row],
    )
    reviewed: list = []
    monkeypatch.setattr(
        guardian,
        "_review_one",
        lambda db, r: reviewed.append(r),  # noqa: ARG005
    )
    fake = _FakeDB(run_task_id=None)
    db = cast(Session, fake)
    assert guardian.drain_guardian_reviews(db) == 1
    assert reviewed == [row]
    assert fake.commits == 1
