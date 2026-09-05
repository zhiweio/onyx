"""Replay persisted Craft chat into a replacement OpenCode session.

When a restored sandbox no longer has the saved ``opencode_session_id``,
Onyx mints a new serve session. This module turns ``BuildMessage`` rows into
a short preamble that the next user prompt carries, so the model keeps
transcript continuity. Disk artifacts remain the long-job source of truth.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol
from uuid import UUID

from sqlalchemy.orm import Session

from onyx.configs.constants import MessageType
from onyx.server.features.build.db.build_session import get_session_messages

REPLAY_CHAR_BUDGET = 16_000
_REPLAY_HEADER = (
    "The previous OpenCode session was replaced after a sandbox restore. "
    "Use this prior transcript as context. Do not greet again. "
    "Continue the work from disk artifacts and this history.\n"
)


class _ReplayMessage(Protocol):
    type: MessageType
    message_metadata: dict[str, object]


def _text_from_content(content: object) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, dict):
        text = content.get("text")
        if isinstance(text, str):
            return text.strip()
    return ""


def _line_from_message(message: _ReplayMessage) -> tuple[str, str] | None:
    metadata = message.message_metadata
    if not isinstance(metadata, dict):
        return None
    meta_type = str(metadata.get("type") or "")
    if message.type == MessageType.USER and meta_type in {"", "user_message"}:
        text = _text_from_content(metadata.get("content"))
        if text:
            return ("User", text)
        return None
    if message.type == MessageType.ASSISTANT and meta_type == "agent_message":
        text = _text_from_content(metadata.get("content"))
        if text:
            return ("Assistant", text)
    return None


def format_replay_preamble(
    messages: list[_ReplayMessage],
    *,
    skip_last_user_text: str | None = None,
) -> str | None:
    """Build a prompt prefix from user/assistant text, or ``None`` if empty.

    Keeps the most recent lines that fit ``REPLAY_CHAR_BUDGET``.
    """
    lines: list[tuple[str, str]] = []
    skip_normalized = (skip_last_user_text or "").strip()
    skipped_current_user = False
    for message in reversed(messages):
        line = _line_from_message(message)
        if line is None:
            continue
        role, text = line
        if (
            not skipped_current_user
            and role == "User"
            and skip_normalized
            and text == skip_normalized
        ):
            skipped_current_user = True
            continue
        lines.append((role, text))
    lines.reverse()
    if not lines:
        return None

    selected: list[str] = []
    used = 0
    for role, text in reversed(lines):
        piece = f"{role}: {text}"
        if used + len(piece) + 1 > REPLAY_CHAR_BUDGET:
            if not selected:
                selected.append(piece[:REPLAY_CHAR_BUDGET])
            break
        selected.append(piece)
        used += len(piece) + 1
    if not selected:
        return None
    selected.reverse()
    return _REPLAY_HEADER + "\n".join(selected)


def apply_replay_preamble(message: str, preamble: str | None) -> str:
    if not preamble:
        return message
    return f"{preamble}\n\nCurrent request:\n{message}"


def message_after_session_replace(
    message: str,
    *,
    previous_session_id: str | None,
    resolved_session_id: str,
    replacement_preamble: Callable[[], str | None] | None,
) -> str:
    """Prefix history only when a persisted OpenCode session was replaced."""
    if previous_session_id is None or resolved_session_id == previous_session_id:
        return message
    preamble = replacement_preamble() if replacement_preamble is not None else None
    return apply_replay_preamble(message, preamble)


def replacement_preamble_for_session(
    db_session: Session,
    session_id: UUID,
    skip_last_user_text: str | None,
) -> str | None:
    messages = get_session_messages(session_id, db_session)
    return format_replay_preamble(messages, skip_last_user_text=skip_last_user_text)
