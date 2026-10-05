"""DAL for craft golden-set eval runs and per-case results.

A run's lifecycle is owned by the eval pipeline
(``onyx/server/features/build/evals/pipeline.py``); these helpers only
touch rows. The pipeline commits — DAL functions never commit on their
own, matching the rest of ``onyx/db``.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from onyx.db.enums import (
    CraftEvalCaseStatus,
    CraftEvalRunStatus,
    CraftEvalRunTrigger,
)
from onyx.db.models import CraftEvalCaseResult, CraftEvalRun
from onyx.utils.logger import setup_logger

logger = setup_logger()


def create_eval_run(
    db_session: Session,
    *,
    trigger: CraftEvalRunTrigger,
    case_slugs: list[str],
    created_by_user_id: UUID | None = None,
    model_provider: str | None = None,
    model_name: str | None = None,
) -> CraftEvalRun:
    """Create a QUEUED run with PENDING per-case rows. Caller commits."""
    run = CraftEvalRun(
        trigger=trigger,
        status=CraftEvalRunStatus.QUEUED,
        created_by_user_id=created_by_user_id,
        case_count=len(case_slugs),
        model_provider=model_provider,
        model_name=model_name,
    )
    db_session.add(run)
    db_session.flush()
    for slug in case_slugs:
        db_session.add(CraftEvalCaseResult(run_id=run.id, case_slug=slug))
    db_session.flush()
    return run


def get_eval_run(db_session: Session, run_id: UUID) -> CraftEvalRun | None:
    return db_session.scalar(select(CraftEvalRun).where(CraftEvalRun.id == run_id))


def get_eval_run_results(
    db_session: Session, run_id: UUID
) -> list[CraftEvalCaseResult]:
    stmt = (
        select(CraftEvalCaseResult)
        .where(CraftEvalCaseResult.run_id == run_id)
        .order_by(CraftEvalCaseResult.id.asc())
    )
    return list(db_session.scalars(stmt))


def get_case_result(
    db_session: Session, run_id: UUID, case_slug: str
) -> CraftEvalCaseResult | None:
    return db_session.scalar(
        select(CraftEvalCaseResult).where(
            CraftEvalCaseResult.run_id == run_id,
            CraftEvalCaseResult.case_slug == case_slug,
        )
    )


def mark_eval_run_status(
    db_session: Session,
    run_id: UUID,
    status: CraftEvalRunStatus,
    *,
    score: float | None = None,
    passed_count: int | None = None,
    error_detail: str | None = None,
    summary: dict[str, Any] | None = None,
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
) -> None:
    run = db_session.get(CraftEvalRun, run_id)
    if run is None:
        logger.warning("mark_eval_run_status: run %s not found", run_id)
        return
    run.status = status
    if score is not None:
        run.score = score
    if passed_count is not None:
        run.passed_count = passed_count
    if error_detail is not None:
        run.error_detail = error_detail[:2000]
    if summary is not None:
        # JSONB reassignment (not in-place mutation) so SQLAlchemy sees it.
        run.summary = summary
    if started_at is not None:
        run.started_at = started_at
    if finished_at is not None:
        run.finished_at = finished_at


def mark_case_result(
    db_session: Session,
    result_id: int,
    *,
    status: CraftEvalCaseStatus | None = None,
    score: float | None = None,
    deterministic_findings: dict[str, Any] | None = None,
    judge_verdict: dict[str, Any] | None = None,
    session_id: UUID | None = None,
    error_detail: str | None = None,
    duration_seconds: float | None = None,
) -> None:
    """Patch-update a case result; only the given fields change."""
    result = db_session.get(CraftEvalCaseResult, result_id)
    if result is None:
        logger.warning("mark_case_result: result %s not found", result_id)
        return
    if status is not None:
        result.status = status
    if score is not None:
        result.score = score
    if deterministic_findings is not None:
        result.deterministic_findings = deterministic_findings
    if judge_verdict is not None:
        result.judge_verdict = judge_verdict
    if session_id is not None:
        result.session_id = session_id
    if error_detail is not None:
        result.error_detail = error_detail[:2000]
    if duration_seconds is not None:
        result.duration_seconds = duration_seconds


def list_eval_runs(db_session: Session, *, limit: int = 50) -> list[CraftEvalRun]:
    stmt = select(CraftEvalRun).order_by(CraftEvalRun.created_at.desc()).limit(limit)
    return list(db_session.scalars(stmt))


def previous_eval_run(
    db_session: Session, before_run: CraftEvalRun
) -> CraftEvalRun | None:
    """Most recent run created strictly before the given run."""
    stmt = (
        select(CraftEvalRun)
        .where(CraftEvalRun.created_at < before_run.created_at)
        .order_by(CraftEvalRun.created_at.desc())
        .limit(1)
    )
    return db_session.scalar(stmt)


def prune_eval_runs_before(db_session: Session, cutoff: datetime) -> int:
    """Delete finished runs older than the cutoff; returns the run count.

    Case results cascade on the FK. Non-terminal runs are never touched.
    """
    result = db_session.execute(
        delete(CraftEvalRun).where(
            CraftEvalRun.created_at < cutoff,
            CraftEvalRun.status.in_(
                [
                    CraftEvalRunStatus.SUCCEEDED,
                    CraftEvalRunStatus.FAILED,
                    CraftEvalRunStatus.REGRESSED,
                ]
            ),
        )
    )
    return int(
        getattr(result, "rowcount", 0) or 0  # ods: ignore[getattr] - Result type varies
    )


def eval_run_retention_cutoff(retention_days: int) -> datetime:
    return datetime.now(tz=timezone.utc) - timedelta(days=retention_days)
