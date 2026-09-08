from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from onyx.auth.permissions import require_permission
from onyx.db.engine.sql_engine import get_session
from onyx.db.enums import Permission
from onyx.db.models import LongTermMemory, User
from onyx.memory.long_term import (
    MemoryFact,
    delete_owned,
    list_for_user,
    update_owned_text,
    upsert_facts,
)
from onyx.server.features.long_term_memory.models import (
    LongTermMemoryCreateRequest,
    LongTermMemoryItem,
    LongTermMemoryListResponse,
    LongTermMemoryPatchRequest,
)

router = APIRouter(prefix="/long-term-memory")


def _item(row: LongTermMemory) -> LongTermMemoryItem:
    return LongTermMemoryItem(
        id=row.id,
        text=row.text,
        kind=row.kind,
        source=row.source,
        source_surface=row.source_surface,
        project_id=row.project_id,
        created_at=row.created_at,
        last_used_at=row.last_used_at,
    )


@router.get("")
def list_long_term_memories(
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    db_session: Session = Depends(get_session),
) -> LongTermMemoryListResponse:
    return LongTermMemoryListResponse(
        items=[_item(row) for row in list_for_user(db_session, user.id)]
    )


@router.post("")
def create_long_term_memory(
    request: LongTermMemoryCreateRequest,
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    db_session: Session = Depends(get_session),
) -> LongTermMemoryItem:
    ids = upsert_facts(
        db_session,
        user.id,
        [MemoryFact(text=request.text, kind=request.kind)],
        source="manual",
        source_surface="chat",
    )
    db_session.commit()
    items = {row.id: row for row in list_for_user(db_session, user.id)}
    created = items.get(ids[0]) if ids else None
    if created is None:
        from onyx.db.long_term_memory import get_owned_active
        from onyx.error_handling.error_codes import OnyxErrorCode
        from onyx.error_handling.exceptions import OnyxError

        if not ids:
            raise OnyxError(OnyxErrorCode.INVALID_INPUT, "Memory was rejected")
        created = get_owned_active(db_session, user.id, ids[0])
        if created is None:
            raise OnyxError(OnyxErrorCode.NOT_FOUND, "Memory not found")
    return _item(created)


@router.patch("/{memory_id}")
def patch_long_term_memory(
    memory_id: int,
    request: LongTermMemoryPatchRequest,
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    db_session: Session = Depends(get_session),
) -> LongTermMemoryItem:
    row = update_owned_text(db_session, user.id, memory_id, request.text)
    db_session.commit()
    return _item(row)


@router.delete("/{memory_id}")
def delete_long_term_memory(
    memory_id: int,
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    db_session: Session = Depends(get_session),
) -> None:
    delete_owned(db_session, user.id, memory_id)
    db_session.commit()
