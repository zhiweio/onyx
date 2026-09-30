"""Ship-gate graduation: supervised approvals promote, rejections reset,
policy-version mismatches void."""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from onyx.db.enums import ApprovalDecision
from onyx.db.models import ActionApproval
from onyx.server.features.build.approvals import graduation


class _FakeDB:
    """Just enough Session for record_decision_outcome.

    execute() with a SELECT-shaped statement → the RUNNING-run lookup (the
    object's ``first()`` yields the task id); execute() with a DELETE-shaped
    statement → a reset. scalar() #1 → the graduation counter lookup;
    scalar() #2 → the existing-pre-approval check. get() → the task row.
    """

    def __init__(
        self,
        *,
        run_task_id: object,
        counter: SimpleNamespace | None = None,
        task: SimpleNamespace | None = None,
    ) -> None:
        self.run_task_id = run_task_id
        self.counter = counter
        self.task = task
        self.added: list[object] = []
        self.object_deletes: list[object] = []
        self.bulk_deletes = 0
        self._scalar_calls = 0

    def execute(self, stmt: object) -> SimpleNamespace:
        from sqlalchemy.sql.dml import Delete

        if isinstance(stmt, Delete):
            self.bulk_deletes += 1
            return SimpleNamespace()
        task_id = self.run_task_id
        return SimpleNamespace(first=lambda: None if task_id is None else (task_id,))

    def scalar(self, _stmt: object) -> SimpleNamespace | None:
        self._scalar_calls += 1
        if self._scalar_calls == 1:
            return self.counter
        return None

    def get(self, _model: type, _task_id: object) -> SimpleNamespace | None:
        return self.task

    def add(self, obj: object) -> None:
        self.added.append(obj)

    def flush(self) -> None:
        return None

    def delete(self, obj: object) -> None:
        self.object_deletes.append(obj)


def _approval(
    *, decision: ApprovalDecision, session_id: object | None = None
) -> SimpleNamespace:
    return SimpleNamespace(
        decision=decision,
        session_id=session_id or uuid4(),
        app_name="Slack",
        gated_app=SimpleNamespace(id=7, policy_version=2),
    )


@pytest.fixture(autouse=True)
def _threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(graduation, "CRAFT_ACTION_GRADUATION_THRESHOLD", 3)
    monkeypatch.setattr(graduation, "CRAFT_ACTION_AUTO_GRADUATION_ENABLED", True)
    monkeypatch.setattr(graduation, "create_notification", lambda **_k: None)


def test_threshold_reached_graduates_to_pre_approval() -> None:
    counter = SimpleNamespace(consecutive_passes=2, policy_version=2, gated_app_id=7)
    task = SimpleNamespace(id=uuid4(), user_id=uuid4(), name="Digest")
    db = _FakeDB(run_task_id=task.id, counter=counter, task=task)
    approval = _approval(decision=ApprovalDecision.APPROVED, session_id=uuid4())

    graduation.record_decision_outcome(
        cast(Session, db),
        decided=cast(ActionApproval, approval),
    )

    grants = [
        obj
        for obj in db.added
        if hasattr(obj, "policy_version") and not hasattr(obj, "consecutive_passes")
    ]
    assert grants
    grant = cast(SimpleNamespace, grants[0])
    assert len(grants) == 1
    assert grant.gated_app_id == 7
    assert grant.policy_version == 2
    assert counter in db.object_deletes  # the counter's job is done


def test_below_threshold_only_bumps_counter() -> None:
    counter = SimpleNamespace(consecutive_passes=0, policy_version=2, gated_app_id=7)
    db = _FakeDB(run_task_id=uuid4(), counter=counter)
    approval = _approval(decision=ApprovalDecision.APPROVED)

    graduation.record_decision_outcome(
        cast(Session, db),
        decided=cast(ActionApproval, approval),
    )

    assert counter.consecutive_passes == 1
    assert db.bulk_deletes == 0


def test_rejection_resets_progress() -> None:
    db = _FakeDB(run_task_id=None)
    approval = _approval(decision=ApprovalDecision.REJECTED)

    graduation.record_decision_outcome(
        cast(Session, db),
        decided=cast(ActionApproval, approval),
    )

    assert db.bulk_deletes == 1


def test_policy_version_mismatch_restarts_count() -> None:
    counter = SimpleNamespace(consecutive_passes=2, policy_version=1, gated_app_id=7)
    db = _FakeDB(run_task_id=uuid4(), counter=counter)
    approval = _approval(decision=ApprovalDecision.APPROVED)

    graduation.record_decision_outcome(
        cast(Session, db),
        decided=cast(ActionApproval, approval),
    )

    # The two stale passes void; this approval is pass 1 under version 2.
    assert counter.consecutive_passes == 1
    assert counter.policy_version == 2
    assert db.object_deletes == []
    assert db.bulk_deletes == 0


def test_non_scheduled_session_is_ignored() -> None:
    db = _FakeDB(run_task_id=None)
    approval = _approval(decision=ApprovalDecision.APPROVED)

    graduation.record_decision_outcome(
        cast(Session, db),
        decided=cast(ActionApproval, approval),
    )

    assert db.added == []
    assert db.object_deletes == []
    assert db.bulk_deletes == 0
