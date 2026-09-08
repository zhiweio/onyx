"""Postgres access for long-term memory. All queries include user_id."""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from onyx.db.models import LongTermMemory

LONG_TERM_MEMORY_EXTRACT_CAP = 3000
NEAR_DUP_DISTANCE = 0.12
_HNSW_DIMS_SEEN: set[int] = set()


@dataclass(frozen=True)
class RecalledMemory:
    id: int
    text: str
    kind: str
    source: str
    source_surface: str
    project_id: UUID | None
    distance: float


def _vector_literal(embedding: list[float]) -> str:
    return "[" + ",".join(f"{float(x):.8f}" for x in embedding) + "]"


def ensure_hnsw_index(db_session: Session, dims: int) -> None:
    if dims < 1 or dims > 8192 or dims in _HNSW_DIMS_SEEN:
        return
    name = f"ix_long_term_memory_hnsw_{dims}"
    db_session.execute(
        text(
            f"""
            CREATE INDEX IF NOT EXISTS {name}
            ON long_term_memory
            USING hnsw ((embedding::vector({int(dims)})) vector_cosine_ops)
            WHERE deleted_at IS NULL AND embedding_dims = {int(dims)}
            """
        )
    )
    _HNSW_DIMS_SEEN.add(dims)


def find_active_by_hash(
    db_session: Session, user_id: UUID, content_hash: str
) -> LongTermMemory | None:
    from sqlalchemy import select

    return db_session.scalar(
        select(LongTermMemory).where(
            LongTermMemory.user_id == user_id,
            LongTermMemory.content_hash == content_hash,
            LongTermMemory.deleted_at.is_(None),
        )
    )


def nearest_neighbor(
    db_session: Session,
    user_id: UUID,
    embedding: list[float],
    embedding_model: str,
) -> tuple[LongTermMemory, float] | None:
    vec = _vector_literal(embedding)
    row = db_session.execute(
        text(
            """
            SELECT id, (embedding <=> CAST(:q AS vector)) AS distance
            FROM long_term_memory
            WHERE user_id = :user_id
              AND deleted_at IS NULL
              AND embedding IS NOT NULL
              AND embedding_model = :embedding_model
            ORDER BY embedding <=> CAST(:q AS vector)
            LIMIT 1
            """
        ),
        {"q": vec, "user_id": user_id, "embedding_model": embedding_model},
    ).first()
    if row is None:
        return None
    memory = db_session.get(LongTermMemory, row.id)
    if memory is None:
        return None
    return memory, float(row.distance)


def insert_memory(
    db_session: Session,
    *,
    user_id: UUID,
    text_value: str,
    content_hash: str,
    kind: str,
    source: str,
    source_surface: str,
    project_id: UUID | None,
    source_session_id: UUID | None,
    embedding: list[float] | None,
    embedding_model: str | None,
    embedding_dims: int | None,
    confidence: float | None = None,
    importance: float | None = None,
) -> LongTermMemory:
    memory = LongTermMemory(
        user_id=user_id,
        project_id=project_id,
        kind=kind,
        text=text_value,
        content_hash=content_hash,
        source=source,
        source_surface=source_surface,
        source_session_id=source_session_id,
        confidence=confidence,
        importance=importance,
        embedding_model=embedding_model,
        embedding_dims=embedding_dims,
    )
    db_session.add(memory)
    db_session.flush()
    if embedding is not None:
        set_embedding(db_session, memory.id, embedding)
    return memory


def set_embedding(
    db_session: Session, memory_id: int, embedding: list[float]
) -> None:
    db_session.execute(
        text(
            """
            UPDATE long_term_memory
            SET embedding = CAST(:q AS vector)
            WHERE id = :id
            """
        ),
        {"q": _vector_literal(embedding), "id": memory_id},
    )


def touch_last_used(db_session: Session, memory_ids: list[int]) -> None:
    if not memory_ids:
        return
    from sqlalchemy import update

    from onyx.db.models import LongTermMemory as LTM

    db_session.execute(
        update(LTM)
        .where(LTM.id.in_(memory_ids))
        .values(last_used_at=datetime.datetime.now(datetime.timezone.utc))
    )


def recall_by_vector(
    db_session: Session,
    *,
    user_id: UUID,
    embedding: list[float],
    embedding_model: str,
    limit: int,
    project_id: UUID | None = None,
) -> list[RecalledMemory]:
    try:
        db_session.execute(text("SET LOCAL hnsw.iterative_scan = 'strict_order'"))
    except Exception:
        pass
    vec = _vector_literal(embedding)
    fetch_limit = max(limit * 2, limit)
    rows = db_session.execute(
        text(
            """
            SELECT id, text, kind, source, source_surface, project_id,
                   (embedding <=> CAST(:q AS vector)) AS distance
            FROM long_term_memory
            WHERE user_id = :user_id
              AND deleted_at IS NULL
              AND embedding IS NOT NULL
              AND embedding_model = :embedding_model
            ORDER BY embedding <=> CAST(:q AS vector)
            LIMIT :lim
            """
        ),
        {
            "q": vec,
            "user_id": user_id,
            "embedding_model": embedding_model,
            "lim": fetch_limit,
        },
    ).all()
    recalled = [
        RecalledMemory(
            id=int(row.id),
            text=str(row.text),
            kind=str(row.kind),
            source=str(row.source),
            source_surface=str(row.source_surface),
            project_id=row.project_id,
            distance=float(row.distance),
        )
        for row in rows
    ]
    if project_id is not None:
        recalled.sort(
            key=lambda item: (
                item.distance - (0.03 if item.project_id == project_id else 0.0)
            )
        )
    return recalled[:limit]


def recall_by_literal(
    db_session: Session, user_id: UUID, query: str, limit: int
) -> list[RecalledMemory]:
    pattern = f"%{query.strip()[:80]}%"
    rows = db_session.execute(
        text(
            """
            SELECT id, text, kind, source, source_surface, project_id
            FROM long_term_memory
            WHERE user_id = :user_id
              AND deleted_at IS NULL
              AND text ILIKE :pattern
            ORDER BY last_used_at DESC
            LIMIT :lim
            """
        ),
        {"user_id": user_id, "pattern": pattern, "lim": limit},
    ).all()
    return [
        RecalledMemory(
            id=int(row.id),
            text=str(row.text),
            kind=str(row.kind),
            source=str(row.source),
            source_surface=str(row.source_surface),
            project_id=row.project_id,
            distance=1.0,
        )
        for row in rows
    ]


def list_active_for_user(
    db_session: Session, user_id: UUID, *, limit: int = 200
) -> list[LongTermMemory]:
    from sqlalchemy import select

    return list(
        db_session.scalars(
            select(LongTermMemory)
            .where(
                LongTermMemory.user_id == user_id,
                LongTermMemory.deleted_at.is_(None),
            )
            .order_by(LongTermMemory.last_used_at.desc())
            .limit(limit)
        ).all()
    )


def get_owned_active(
    db_session: Session, user_id: UUID, memory_id: int
) -> LongTermMemory | None:
    from sqlalchemy import select

    return db_session.scalar(
        select(LongTermMemory).where(
            LongTermMemory.id == memory_id,
            LongTermMemory.user_id == user_id,
            LongTermMemory.deleted_at.is_(None),
        )
    )


def soft_delete(db_session: Session, memory: LongTermMemory) -> None:
    memory.deleted_at = datetime.datetime.now(datetime.timezone.utc)


def count_extract_rows(db_session: Session, user_id: UUID) -> int:
    from sqlalchemy import func, select

    return int(
        db_session.scalar(
            select(func.count())
            .select_from(LongTermMemory)
            .where(
                LongTermMemory.user_id == user_id,
                LongTermMemory.deleted_at.is_(None),
                LongTermMemory.source == "extract",
            )
        )
        or 0
    )


def evict_oldest_extract(db_session: Session, user_id: UUID) -> None:
    from sqlalchemy import select

    oldest = db_session.scalar(
        select(LongTermMemory)
        .where(
            LongTermMemory.user_id == user_id,
            LongTermMemory.deleted_at.is_(None),
            LongTermMemory.source == "extract",
        )
        .order_by(LongTermMemory.last_used_at.asc())
        .limit(1)
    )
    if oldest is not None:
        soft_delete(db_session, oldest)


def list_stale_embeddings(
    db_session: Session, user_id: UUID, current_model: str, *, limit: int = 16
) -> list[LongTermMemory]:
    from sqlalchemy import or_, select

    return list(
        db_session.scalars(
            select(LongTermMemory)
            .where(
                LongTermMemory.user_id == user_id,
                LongTermMemory.deleted_at.is_(None),
                or_(
                    LongTermMemory.embedding_model.is_(None),
                    LongTermMemory.embedding_model != current_model,
                ),
            )
            .order_by(LongTermMemory.last_used_at.desc())
            .limit(limit)
        ).all()
    )
