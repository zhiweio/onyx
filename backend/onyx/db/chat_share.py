from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from onyx.db.enums import ChatSessionSharePermission, ChatSessionSharedStatus
from onyx.db.models import (
    ChatSession,
    ChatSession__User,
    ChatSession__UserGroup,
    User__UserGroup,
)


def _group_ids_for_user(db_session: Session, user_id: UUID) -> list[int]:
    return list(
        db_session.scalars(
            select(User__UserGroup.user_group_id).where(
                User__UserGroup.user_id == user_id
            )
        ).all()
    )


def user_can_view_chat_session(
    db_session: Session,
    chat_session: ChatSession,
    user_id: UUID | None,
) -> bool:
    if user_id is None:
        return chat_session.shared_status == ChatSessionSharedStatus.PUBLIC
    if chat_session.user_id in (user_id, None):
        return True
    if chat_session.shared_status == ChatSessionSharedStatus.PUBLIC:
        return True
    user_share = db_session.scalar(
        select(ChatSession__User.user_id).where(
            ChatSession__User.chat_session_id == chat_session.id,
            ChatSession__User.user_id == user_id,
        )
    )
    if user_share is not None:
        return True
    group_ids = _group_ids_for_user(db_session, user_id)
    if not group_ids:
        return False
    group_share = db_session.scalar(
        select(ChatSession__UserGroup.user_group_id).where(
            ChatSession__UserGroup.chat_session_id == chat_session.id,
            ChatSession__UserGroup.user_group_id.in_(group_ids),
        )
    )
    return group_share is not None


def chat_session_visible_to_user_clause(user_id: UUID):
    group_ids = select(User__UserGroup.user_group_id).where(
        User__UserGroup.user_id == user_id
    )
    return or_(
        ChatSession.user_id == user_id,
        ChatSession.user_id.is_(None),
        ChatSession.shared_status == ChatSessionSharedStatus.PUBLIC,
        ChatSession.id.in_(
            select(ChatSession__User.chat_session_id).where(
                ChatSession__User.user_id == user_id
            )
        ),
        ChatSession.id.in_(
            select(ChatSession__UserGroup.chat_session_id).where(
                ChatSession__UserGroup.user_group_id.in_(group_ids)
            )
        ),
    )


def replace_chat_session_shares(
    db_session: Session,
    chat_session: ChatSession,
    user_ids: list[UUID],
    group_ids: list[int],
) -> ChatSession:
    db_session.query(ChatSession__User).filter(
        ChatSession__User.chat_session_id == chat_session.id
    ).delete()
    db_session.query(ChatSession__UserGroup).filter(
        ChatSession__UserGroup.chat_session_id == chat_session.id
    ).delete()
    for uid in user_ids:
        db_session.add(
            ChatSession__User(
                chat_session_id=chat_session.id,
                user_id=uid,
                permission=ChatSessionSharePermission.VIEWER,
            )
        )
    for gid in group_ids:
        db_session.add(
            ChatSession__UserGroup(
                chat_session_id=chat_session.id,
                user_group_id=gid,
                permission=ChatSessionSharePermission.VIEWER,
            )
        )
    if user_ids or group_ids:
        if chat_session.shared_status != ChatSessionSharedStatus.PUBLIC:
            chat_session.shared_status = ChatSessionSharedStatus.SHARED
    elif chat_session.shared_status == ChatSessionSharedStatus.SHARED:
        chat_session.shared_status = ChatSessionSharedStatus.PRIVATE
    db_session.add(chat_session)
    db_session.commit()
    db_session.refresh(chat_session)
    return chat_session


def list_chat_session_shares(
    db_session: Session, chat_session_id: UUID
) -> tuple[list[ChatSession__User], list[ChatSession__UserGroup]]:
    users = list(
        db_session.scalars(
            select(ChatSession__User).where(
                ChatSession__User.chat_session_id == chat_session_id
            )
        ).all()
    )
    groups = list(
        db_session.scalars(
            select(ChatSession__UserGroup).where(
                ChatSession__UserGroup.chat_session_id == chat_session_id
            )
        ).all()
    )
    return users, groups
