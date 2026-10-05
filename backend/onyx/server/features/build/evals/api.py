"""Admin API for the craft golden-set eval pipeline (P4).

Mounted under ``/build/admin/evals`` (full admin panel access): browse the
built-in case catalog, trigger runs (full set or a subset), and inspect
run/case results including the judge's per-criterion evidence and the
diff against the previous run.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from onyx.auth.permissions import require_permission
from onyx.background.celery.versioned_apps.client import app as celery_app
from onyx.configs.constants import (
    OnyxCeleryPriority,
    OnyxCeleryQueues,
    OnyxCeleryTask,
)
from onyx.db.craft_evals import (
    get_eval_run,
    get_eval_run_results,
    list_eval_runs,
)
from onyx.db.engine.sql_engine import get_session
from onyx.db.enums import CraftEvalRunTrigger, Permission, SessionOrigin
from onyx.db.models import BuildSession, User
from onyx.error_handling.error_codes import OnyxErrorCode
from onyx.error_handling.exceptions import OnyxError
from onyx.server.features.build.configs import CRAFT_EVAL_ENABLED
from onyx.server.features.build.db.build_session import get_session_messages
from onyx.server.features.build.evals.pipeline import create_eval_run_for_cases
from onyx.server.features.build.session.models import (
    MessageListResponse,
    MessageResponse,
)
from onyx.system_catalog.builtin.evals.loader import load_builtin_eval_cases

admin_router = APIRouter(prefix="/evals")


def _require_eval_enabled() -> None:
    if not CRAFT_EVAL_ENABLED:
        raise OnyxError(
            OnyxErrorCode.INSUFFICIENT_PERMISSIONS,
            "Craft evals are disabled (CRAFT_EVAL_ENABLED=false)",
        )


class EvalCaseSummary(BaseModel):
    slug: str
    name: str
    domain: str
    scenario_slug: str | None
    skill_slugs: list[str]
    report_contract_slug: str | None
    budget_seconds: int
    expected_paths: list[str]
    rubric_criterion_count: int
    value_anchor_count: int


class EvalRunCaseResult(BaseModel):
    case_slug: str
    case_name: str
    domain: str
    status: str
    score: float | None
    duration_seconds: float | None
    session_id: str | None
    error_detail: str | None
    deterministic_findings: dict[str, Any]
    judge_verdict: dict[str, Any]


class EvalRunSummary(BaseModel):
    id: str
    trigger: str
    status: str
    case_count: int
    passed_count: int
    score: float | None
    model_provider: str | None
    model_name: str | None
    error_detail: str | None
    created_at: datetime
    finished_at: datetime | None


class EvalRunDetail(EvalRunSummary):
    summary: dict[str, Any]
    case_results: list[EvalRunCaseResult]


class EvalRunCreateRequest(BaseModel):
    case_slugs: list[str] | None = Field(
        default=None,
        description="Subset of case slugs; omit for the full built-in set.",
    )


@admin_router.get("/cases")
def list_cases(
    _: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
) -> list[EvalCaseSummary]:
    _require_eval_enabled()
    return [
        EvalCaseSummary(
            slug=case.slug,
            name=case.name,
            domain=case.domain,
            scenario_slug=case.scenario_slug,
            skill_slugs=list(case.skill_slugs),
            report_contract_slug=case.report_contract_slug,
            budget_seconds=case.budget_seconds,
            expected_paths=list(case.expected_paths),
            rubric_criterion_count=len(case.rubric),
            value_anchor_count=len(case.value_anchors),
        )
        for case in load_builtin_eval_cases().values()
    ]


@admin_router.post("/runs")
def trigger_run(
    request: EvalRunCreateRequest,
    user: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> EvalRunDetail:
    _require_eval_enabled()
    try:
        run, _cases = create_eval_run_for_cases(
            db_session,
            trigger=CraftEvalRunTrigger.MANUAL,
            case_slugs=request.case_slugs,
            created_by_user_id=user.id,
        )
        db_session.commit()
    except KeyError as exc:
        raise OnyxError(OnyxErrorCode.INVALID_INPUT, str(exc).strip("'")) from exc

    from shared_configs.contextvars import get_current_tenant_id

    celery_app.send_task(
        OnyxCeleryTask.CRAFT_EVAL_RUN,
        kwargs={"run_id": str(run.id), "tenant_id": get_current_tenant_id()},
        queue=OnyxCeleryQueues.SCHEDULED_TASKS,
        priority=OnyxCeleryPriority.MEDIUM,
    )
    return _run_detail_payload(run, db_session)


@admin_router.get("/runs")
def list_runs(
    limit: int = Query(default=20, ge=1, le=100),
    _: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> list[EvalRunSummary]:
    _require_eval_enabled()
    return [
        _run_summary_payload(run) for run in list_eval_runs(db_session, limit=limit)
    ]


@admin_router.get("/runs/{run_id}")
def get_run(
    run_id: UUID,
    _: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> EvalRunDetail:
    _require_eval_enabled()
    run = get_eval_run(db_session, run_id)
    if run is None:
        raise OnyxError(OnyxErrorCode.NOT_FOUND, "Eval run not found")
    return _run_detail_payload(run, db_session)


@admin_router.get("/sessions/{session_id}/messages")
def list_eval_session_messages(
    session_id: UUID,
    _: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> MessageListResponse:
    """Read-only transcript of a headless eval session.

    Eval sessions are owned by the dedicated eval service account, so the
    regular per-user session endpoints 404 for every admin. Surfacing the
    transcript here keeps craft's per-user ownership model untouched.
    """
    _require_eval_enabled()
    build_session = db_session.get(BuildSession, session_id)
    if build_session is None or build_session.origin != SessionOrigin.EVAL:
        raise OnyxError(OnyxErrorCode.NOT_FOUND, "Eval session not found")
    return MessageListResponse(
        messages=[
            MessageResponse.from_model(message)
            for message in get_session_messages(session_id, db_session)
        ]
    )


def _run_summary_payload(run: Any) -> EvalRunSummary:
    return EvalRunSummary(
        id=str(run.id),
        trigger=run.trigger.value
        if hasattr(run.trigger, "value")
        else str(run.trigger),
        status=run.status.value if hasattr(run.status, "value") else str(run.status),
        case_count=run.case_count,
        passed_count=run.passed_count,
        score=run.score,
        model_provider=run.model_provider,
        model_name=run.model_name,
        error_detail=run.error_detail,
        created_at=run.created_at,
        finished_at=run.finished_at,
    )


def _run_detail_payload(run: Any, db_session: Session) -> EvalRunDetail:
    catalog = load_builtin_eval_cases()
    results = []
    for result in get_eval_run_results(db_session, run.id):
        case = catalog.get(result.case_slug)
        results.append(
            EvalRunCaseResult(
                case_slug=result.case_slug,
                case_name=case.name if case else result.case_slug,
                domain=case.domain if case else "",
                status=(
                    result.status.value
                    if hasattr(result.status, "value")
                    else str(result.status)
                ),
                score=result.score,
                duration_seconds=result.duration_seconds,
                session_id=str(result.session_id) if result.session_id else None,
                error_detail=result.error_detail,
                deterministic_findings=result.deterministic_findings or {},
                judge_verdict=result.judge_verdict or {},
            )
        )
    return EvalRunDetail(
        **_run_summary_payload(run).model_dump(),
        summary=run.summary or {},
        case_results=results,
    )
