"""Park an OpenCode question until the user picks chips.

OpenCode 1.18+ emits ``question.asked`` (id ``que_*``) and replies at
``/session/{id}/question/{id}/reply``. Older builds used
``permission.asked`` with ``permission=question``.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ValidationError

from onyx.cache.interface import CacheBackend
from onyx.utils.logger import setup_logger

logger = setup_logger()

_ANNOUNCE_TTL_S = 60
_PENDING_TTL_S = 60 * 30


class QuestionAskItem(BaseModel):
    prompt: str
    options: list[str] = []


class QuestionAskRequest(BaseModel):
    request_id: str
    prompt: str
    options: list[str] = []
    questions: list[QuestionAskItem] = []


class QuestionAskPending(BaseModel):
    build_session_id: str
    opencode_session_id: str
    perm_id: str
    directory: str
    kind: Literal["question", "permission"] = "permission"


def _announce_key(session_id: str) -> str:
    return f"craft:question_ask:announce:{session_id}"


def _pending_key(request_id: str) -> str:
    return f"craft:question_ask:pending:{request_id}"


def _current_key(session_id: str) -> str:
    return f"craft:question_ask:current:{session_id}"


def _seen_key(session_id: str) -> str:
    return f"craft:question_ask:seen:{session_id}"


def _unseen_timeout_key(session_id: str) -> str:
    return f"craft:question_ask:unseen_timeout:{session_id}"


def announce_request(
    session_id: str, request: QuestionAskRequest, cache: CacheBackend
) -> None:
    key = _announce_key(session_id)
    cache.rpush(key, request.model_dump_json())
    cache.expire(key, _ANNOUNCE_TTL_S)
    set_current(session_id, request, cache)


def pop_announcement(
    session_id: str, timeout_s: int, cache: CacheBackend
) -> QuestionAskRequest | None:
    result = cache.blpop([_announce_key(session_id)], timeout_s)
    if result is None:
        return None
    _key, value = result
    if isinstance(value, bytes):
        value = value.decode()
    try:
        return QuestionAskRequest.model_validate_json(value)
    except ValidationError:
        logger.warning("question_ask: unparseable announce %r for %s", value, session_id)
        return None


def stash_pending(
    request_id: str, pending: QuestionAskPending, cache: CacheBackend
) -> None:
    cache.set(_pending_key(request_id), pending.model_dump_json(), ex=_PENDING_TTL_S)


def load_pending(request_id: str, cache: CacheBackend) -> QuestionAskPending | None:
    raw = cache.get(_pending_key(request_id))
    if raw is None:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode()
    try:
        return QuestionAskPending.model_validate_json(raw)
    except ValidationError:
        logger.warning("question_ask: unparseable pending for %s", request_id)
        return None


def clear_pending(request_id: str, cache: CacheBackend) -> None:
    cache.delete(_pending_key(request_id))


def set_current(
    session_id: str, request: QuestionAskRequest, cache: CacheBackend
) -> None:
    cache.set(_current_key(session_id), request.model_dump_json(), ex=_PENDING_TTL_S)


def load_current(session_id: str, cache: CacheBackend) -> QuestionAskRequest | None:
    raw = cache.get(_current_key(session_id))
    if raw is None:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode()
    try:
        return QuestionAskRequest.model_validate_json(raw)
    except ValidationError:
        logger.warning("question_ask: unparseable current for %s", session_id)
        return None


def clear_current(session_id: str, cache: CacheBackend) -> None:
    cache.delete(_current_key(session_id))
    cache.delete(_seen_key(session_id))


def mark_seen(session_id: str, cache: CacheBackend) -> None:
    cache.set(_seen_key(session_id), "1", ex=_PENDING_TTL_S)


def was_seen(session_id: str, cache: CacheBackend) -> bool:
    return cache.get(_seen_key(session_id)) is not None


def mark_unseen_timeout(session_id: str, cache: CacheBackend) -> None:
    cache.set(_unseen_timeout_key(session_id), "1", ex=_PENDING_TTL_S)


def take_unseen_timeout(session_id: str, cache: CacheBackend) -> bool:
    key = _unseen_timeout_key(session_id)
    if cache.get(key) is None:
        return False
    cache.delete(key)
    return True


def _option_labels(raw_opts: object) -> list[str]:
    labels: list[str] = []
    if not isinstance(raw_opts, list):
        return labels
    for opt in raw_opts:
        if isinstance(opt, str) and opt.strip():
            labels.append(opt.strip())
        elif isinstance(opt, dict):
            label = str(opt.get("label") or opt.get("title") or "").strip()
            if label:
                labels.append(label)
    return labels


def _item_from_mapping(raw: dict[str, Any]) -> QuestionAskItem | None:
    prompt = str(
        raw.get("question") or raw.get("header") or raw.get("prompt") or ""
    ).strip()
    options = _option_labels(raw.get("options"))
    if not prompt and not options:
        return None
    return QuestionAskItem(prompt=prompt or "Need a choice.", options=options)


def questions_from_props(props: dict[str, Any]) -> list[QuestionAskItem]:
    meta = props.get("metadata")
    meta = meta if isinstance(meta, dict) else {}
    raw_questions = meta.get("questions") or props.get("questions") or []
    items: list[QuestionAskItem] = []
    if isinstance(raw_questions, list):
        for raw in raw_questions:
            if isinstance(raw, dict):
                item = _item_from_mapping(raw)
                if item is not None:
                    items.append(item)
    if items:
        return items
    prompt = str(meta.get("question") or props.get("message") or "").strip()
    options = _option_labels(meta.get("options") or props.get("options"))
    if prompt or options:
        return [QuestionAskItem(prompt=prompt or "Need a choice.", options=options)]
    return []


def prompt_and_options(props: dict[str, Any]) -> tuple[str, list[str]]:
    items = questions_from_props(props)
    if items:
        return items[0].prompt, list(items[0].options)
    return "Need a choice.", []


def normalize_answers(
    answers: list[list[str]] | None, answer: str | None
) -> list[list[str]]:
    if answers:
        return [[label.strip() for label in row if label.strip()] for row in answers]
    if answer and answer.strip():
        return [[answer.strip()]]
    return []
