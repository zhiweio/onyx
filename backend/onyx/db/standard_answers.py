"""Standard answer DAL: paginated admin list queries."""

from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from onyx.db.models import (
    StandardAnswer,
    StandardAnswer__StandardAnswerCategory,
)


def _answer_conditions(*, q: str | None, category_id: int | None) -> list:
    conditions = []
    if q:
        pattern = f"%{q}%"
        conditions.append(
            or_(
                StandardAnswer.keyword.ilike(pattern),
                StandardAnswer.answer.ilike(pattern),
            )
        )
    if category_id is not None:
        conditions.append(
            StandardAnswer.id.in_(
                select(StandardAnswer__StandardAnswerCategory.standard_answer_id).where(
                    StandardAnswer__StandardAnswerCategory.standard_answer_category_id
                    == category_id
                )
            )
        )
    return conditions


def list_standard_answers(
    db_session: Session,
    *,
    q: str | None = None,
    category_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[StandardAnswer]:
    stmt = select(StandardAnswer).where(
        *_answer_conditions(q=q, category_id=category_id)
    )
    stmt = stmt.order_by(StandardAnswer.keyword.asc()).limit(limit).offset(offset)
    return list(db_session.scalars(stmt).all())


def count_standard_answers(
    db_session: Session,
    *,
    q: str | None = None,
    category_id: int | None = None,
) -> int:
    stmt = (
        select(func.count())
        .select_from(StandardAnswer)
        .where(*_answer_conditions(q=q, category_id=category_id))
    )
    return int(db_session.scalar(stmt) or 0)
