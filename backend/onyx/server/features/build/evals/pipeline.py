"""Craft eval pipeline orchestration: create runs, execute them case by
case, aggregate scores, and diff against the previous run for regression
tracking. The Celery task in ``background/celery/tasks/craft_evals`` is a
thin wrapper around ``run_eval_pipeline`` so tests can drive it without a
worker (same split as scheduled tasks).
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from onyx.db.craft_evals import (
    create_eval_run,
    get_eval_run,
    get_eval_run_results,
    list_eval_runs,
    mark_case_result,
    mark_eval_run_status,
    previous_eval_run,
)
from onyx.db.engine.sql_engine import get_session_with_current_tenant
from onyx.db.enums import (
    CraftEvalCaseStatus,
    CraftEvalRunStatus,
    CraftEvalRunTrigger,
)
from onyx.db.llm import fetch_default_llm_model
from onyx.server.features.build.configs import CRAFT_EVAL_PASS_THRESHOLD
from onyx.server.features.build.evals.runner import run_eval_case
from onyx.server.metrics.craft_evals import (
    record_case_outcome,
    record_run_duration,
)
from onyx.system_catalog.builtin.evals.loader import (
    EvalCase,
    load_builtin_eval_cases,
)
from onyx.utils.logger import setup_logger

logger = setup_logger()

# A per-case score drop beyond this vs the previous run flags a regression
# in the run summary even when the run still clears the threshold.
_CASE_REGRESSION_DELTA = 0.1


def create_eval_run_for_cases(
    db_session: Session,
    *,
    trigger: CraftEvalRunTrigger,
    case_slugs: list[str] | None = None,
    created_by_user_id: UUID | None = None,
) -> tuple[Any, list[EvalCase]]:
    """Validate case selection and create the QUEUED run (caller commits).

    Returns (run, cases). Raises ``KeyError`` naming the first unknown slug.
    """
    catalog = load_builtin_eval_cases()
    if case_slugs is None:
        ordered = list(catalog.values())
    else:
        if not case_slugs:
            raise KeyError("case selection is empty")
        ordered = []
        for slug in case_slugs:
            case = catalog.get(slug)
            if case is None:
                raise KeyError(f"unknown eval case: {slug}")
            ordered.append(case)

    default_model = fetch_default_llm_model(db_session)
    model_name = default_model.name if default_model else None
    model_provider = None
    if default_model is not None and default_model.llm_provider is not None:
        model_provider = default_model.llm_provider.name

    run = create_eval_run(
        db_session,
        trigger=trigger,
        case_slugs=[c.slug for c in ordered],
        created_by_user_id=created_by_user_id,
        model_provider=model_provider,
        model_name=model_name,
    )
    return run, ordered


def run_eval_pipeline(run_id: UUID) -> None:
    """Execute a QUEUED run to a terminal status. Never raises: the worst
    failure marks the run FAILED with detail."""
    started = time.monotonic()
    try:
        with get_session_with_current_tenant() as db_session:
            run = get_eval_run(db_session, run_id)
            if run is None or run.status != CraftEvalRunStatus.QUEUED:
                logger.info(
                    "Eval run %s not QUEUED; nothing to do.", run_id
                )
                return
            results = get_eval_run_results(db_session, run_id)
            mark_eval_run_status(
                db_session,
                run_id,
                CraftEvalRunStatus.RUNNING,
                started_at=datetime.now(tz=timezone.utc),
            )
            db_session.commit()

        catalog = load_builtin_eval_cases()
        for result in results:
            case = catalog.get(result.case_slug)
            if case is None:
                mark_result_error(
                    result.id, f"case definition missing: {result.case_slug}"
                )
                record_case_outcome("error")
                continue
            run_eval_case(run_id, result.id, case)

        _finalize_run(run_id, duration=time.monotonic() - started)
    except Exception:
        logger.exception("Eval run %s crashed", run_id)
        try:
            with get_session_with_current_tenant() as db_session:
                current = get_eval_run(db_session, run_id)
                if current is not None and not current.status.is_terminal():
                    mark_eval_run_status(
                        db_session,
                        run_id,
                        CraftEvalRunStatus.FAILED,
                        error_detail="pipeline crashed (see worker logs)",
                        finished_at=datetime.now(tz=timezone.utc),
                    )
                    db_session.commit()
        except Exception:
            logger.exception(
                "Failed to mark eval run %s FAILED after crash", run_id
            )


def _finalize_run(run_id: UUID, *, duration: float) -> None:
    with get_session_with_current_tenant() as db_session:
        run = get_eval_run(db_session, run_id)
        if run is None:
            return
        results = get_eval_run_results(db_session, run_id)
        previous = previous_eval_run(db_session, run)

        scores = {
            r.case_slug: (r.score if r.score is not None else 0.0)
            for r in results
        }
        statuses = {r.case_slug: r.status for r in results}
        passed = sum(
            1 for status in statuses.values() if status == CraftEvalCaseStatus.PASS
        )
        errors = sum(
            1 for status in statuses.values() if status == CraftEvalCaseStatus.ERROR
        )
        score = (
            sum(scores.values()) / len(results) if results else 0.0
        )

        summary: dict[str, Any] = {
            "case_scores": {k: round(v, 4) for k, v in scores.items()},
            "case_statuses": {k: v.value for k, v in statuses.items()},
            "pass_threshold": CRAFT_EVAL_PASS_THRESHOLD,
        }
        regressions: list[dict[str, Any]] = []
        if previous is not None:
            prev_results = get_eval_run_results(db_session, previous.id)
            prev_scores = {
                r.case_slug: (r.score if r.score is not None else 0.0)
                for r in prev_results
            }
            prev_statuses = {r.case_slug: r.status for r in prev_results}
            summary["previous_run_id"] = str(previous.id)
            summary["previous_score"] = previous.score
            for slug, current_score in scores.items():
                prev_score = prev_scores.get(slug)
                if prev_score is None:
                    continue
                dropped = prev_score - current_score
                prev_pass = prev_statuses.get(slug) == CraftEvalCaseStatus.PASS
                now_pass = statuses.get(slug) == CraftEvalCaseStatus.PASS
                if dropped >= _CASE_REGRESSION_DELTA or (prev_pass and not now_pass):
                    regressions.append(
                        {
                            "case": slug,
                            "previous_score": round(prev_score, 4),
                            "score": round(current_score, 4),
                        }
                    )
        if regressions:
            summary["regressions"] = regressions

        if results and errors == len(results):
            status = CraftEvalRunStatus.FAILED
        elif score < CRAFT_EVAL_PASS_THRESHOLD:
            status = CraftEvalRunStatus.REGRESSED
        else:
            status = CraftEvalRunStatus.SUCCEEDED

        mark_eval_run_status(
            db_session,
            run_id,
            status,
            score=round(score, 4),
            passed_count=passed,
            summary=summary,
            finished_at=datetime.now(tz=timezone.utc),
        )
        db_session.commit()

        record_run_duration(duration)
        _maybe_notify(run_id, run, status, regressions, db_session)


def _maybe_notify(
    run_id: UUID,
    run: Any,
    status: CraftEvalRunStatus,
    regressions: list[dict[str, Any]],
    db_session: Session,
) -> None:
    """Manual runs notify their triggerer on failure/regression. Nightly
    runs surface via logs + metrics only (no per-user owner to notify)."""
    if run.trigger != CraftEvalRunTrigger.MANUAL:
        return
    if run.created_by_user_id is None:
        return
    if status == CraftEvalRunStatus.SUCCEEDED and not regressions:
        return
    from onyx.configs.constants import NotificationType
    from onyx.db.notification import create_notification

    try:
        create_notification(
            user_id=run.created_by_user_id,
            notif_type=NotificationType.CRAFT_EVAL_RUN_ALERT,
            db_session=db_session,
            title=f'Craft eval run "{run_id}" finished: {status.value}',
            additional_data={
                "run_id": str(run_id),
                "score": run.score,
                "regressions": regressions[:10],
            },
            autocommit=False,
        )
        db_session.commit()
    except Exception:
        logger.exception("eval run notification failed (run=%s)", run_id)


def mark_result_error(result_id: int, detail: str) -> None:
    with get_session_with_current_tenant() as db_session:
        mark_case_result(
            db_session,
            result_id,
            status=CraftEvalCaseStatus.ERROR,
            error_detail=detail,
        )
        db_session.commit()


def latest_runs(db_session: Session, limit: int = 50) -> list[Any]:
    return list_eval_runs(db_session, limit=limit)
