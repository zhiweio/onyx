"""Community Edition standard answers admin API.

The tables have always lived in CE (the Slack bot's short-circuit path
reads them); this router supplies the management REST shapes the
web UI speaks.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from onyx.auth.permissions import require_permission
from onyx.db.engine.sql_engine import get_session
from onyx.db.enums import Permission
from onyx.db.models import (
    StandardAnswer,
    StandardAnswerCategory,
    StandardAnswer__StandardAnswerCategory,
    User,
)
from onyx.error_handling.error_codes import OnyxErrorCode
from onyx.error_handling.exceptions import OnyxError

router = APIRouter(prefix="/admin/standard-answers")


class StandardAnswerCreateRequest(BaseModel):
    keyword: str
    answer: str
    active: bool = True
    match_regex: bool = False
    match_any_keywords: bool = False
    category_ids: list[int] = []


class StandardAnswerUpdateRequest(BaseModel):
    keyword: str | None = None
    answer: str | None = None
    active: bool | None = None
    match_regex: bool | None = None
    match_any_keywords: bool | None = None
    category_ids: list[int] | None = None


class CategoryCreateRequest(BaseModel):
    name: str


def _serialize(row: StandardAnswer) -> dict[str, Any]:
    return {
        "id": row.id,
        "keyword": row.keyword,
        "answer": row.answer,
        "active": row.active,
        "match_regex": row.match_regex,
        "match_any_keywords": row.match_any_keywords,
        "category_ids": [cat.id for cat in row.categories],
    }


def _serialize_category(row: StandardAnswerCategory) -> dict[str, Any]:
    return {"id": row.id, "name": row.name}


@router.get("")
def list_answers(
    user: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),  # noqa: ARG001
    db_session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    rows = db_session.scalars(select(StandardAnswer)).all()
    return [_serialize(row) for row in rows]


@router.get("/categories")
def list_categories(
    user: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),  # noqa: ARG001
    db_session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    rows = db_session.scalars(select(StandardAnswerCategory)).all()
    return [_serialize_category(row) for row in rows]


@router.post("/categories")
def create_category(
    request: CategoryCreateRequest,
    user: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),  # noqa: ARG001
    db_session: Session = Depends(get_session),
) -> dict[str, Any]:
    name = request.name.strip()
    if not name:
        raise OnyxError(OnyxErrorCode.VALIDATION_ERROR, "category name is required")
    clash = db_session.scalar(
        select(StandardAnswerCategory.id).where(StandardAnswerCategory.name == name)
    )
    if clash is not None:
        raise OnyxError(OnyxErrorCode.CONFLICT, f"category {name!r} already exists")
    row = StandardAnswerCategory(name=name)
    db_session.add(row)
    db_session.commit()
    return _serialize_category(row)


@router.post("")
def create_answer(
    request: StandardAnswerCreateRequest,
    user: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),  # noqa: ARG001
    db_session: Session = Depends(get_session),
) -> dict[str, Any]:
    keyword = request.keyword.strip()
    if not keyword or not request.answer.strip():
        raise OnyxError(
            OnyxErrorCode.VALIDATION_ERROR, "keyword and answer are required"
        )
    row = StandardAnswer(
        keyword=keyword,
        answer=request.answer,
        active=request.active,
        match_regex=request.match_regex,
        match_any_keywords=request.match_any_keywords,
    )
    _set_categories(db_session, row, request.category_ids)
    db_session.add(row)
    db_session.commit()
    return _serialize(row)


@router.patch("/{answer_id}")
def update_answer(
    answer_id: int,
    request: StandardAnswerUpdateRequest,
    user: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),  # noqa: ARG001
    db_session: Session = Depends(get_session),
) -> dict[str, Any]:
    row = db_session.get(StandardAnswer, answer_id)
    if row is None:
        raise OnyxError(OnyxErrorCode.NOT_FOUND, f"standard answer {answer_id} not found")
    if request.keyword is not None:
        row.keyword = request.keyword.strip()
    if request.answer is not None:
        row.answer = request.answer
    if request.active is not None:
        row.active = request.active
    if request.match_regex is not None:
        row.match_regex = request.match_regex
    if request.match_any_keywords is not None:
        row.match_any_keywords = request.match_any_keywords
    if request.category_ids is not None:
        _set_categories(db_session, row, request.category_ids)
    db_session.commit()
    return _serialize(row)


@router.delete("/{answer_id}")
def delete_answer(
    answer_id: int,
    user: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),  # noqa: ARG001
    db_session: Session = Depends(get_session),
) -> dict[str, Any]:
    row = db_session.get(StandardAnswer, answer_id)
    if row is None:
        raise OnyxError(OnyxErrorCode.NOT_FOUND, f"standard answer {answer_id} not found")
    db_session.delete(row)
    db_session.commit()
    return {"success": True}


def _set_categories(
    db_session: Session, row: StandardAnswer, category_ids: list[int]
) -> None:
    if category_ids:
        categories = (
            db_session.scalars(
                select(StandardAnswerCategory).where(
                    StandardAnswerCategory.id.in_(category_ids)
                )
            ).all()
        )
        found = {cat.id for cat in categories}
        missing = set(category_ids) - found
        if missing:
            raise OnyxError(
                OnyxErrorCode.VALIDATION_ERROR,
                f"unknown category ids: {sorted(missing)}",
            )
        row.categories = list(categories)
    else:
        row.categories = []
