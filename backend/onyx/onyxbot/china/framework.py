"""China IM bot framework: callback processing shared by all platforms.

Flow per inbound callback (the platform requires a fast 1-5s reply, so
verification and URL echo answer inline; message answering runs in a
background thread):

    verify signature/decrypt → dedup on msg id (Redis SETNX)
    → URL-verification echo (inline)
    → parse message → record user binding (platform id ↔ Onyx user)
    → background: provision user (deterministic SSO email convention)
      → in-process chat (handle_stream_message_objects + gather_stream)
      → platform reply

Push notifications (approval cards, loop-held outputs) look up the
binding and DM the user through the same reply senders.
"""

from __future__ import annotations

import datetime
import io
import json
import re
import threading
import time
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from onyx.configs.constants import FileOrigin
from onyx.utils.logger import setup_logger

logger = setup_logger()

# Bound concurrent background answers per api_server process; the
# platform retries callbacks, so overflow is dropped with a log.
_MAX_CONCURRENT_ANSWERS = 8
_answer_semaphore = threading.Semaphore(_MAX_CONCURRENT_ANSWERS)

BOT_EMAIL_DOMAIN_FALLBACK = "im.local"

# Slash commands that start a fresh chat session on the next message.
_RESET_COMMANDS = frozenset({"/reset", "/new", "/新对话", "新对话"})
_RESET_FLAG_TTL_SECONDS = 7 * 24 * 3600

# Slash commands answered directly (menu items send these as messages).
# Feishu's custom menu sends the item name as the message, so the friendly
# menu labels double as command aliases.
_HELP_COMMANDS = frozenset({"/help", "/帮助", "帮助", "使用帮助"})
_SCENARIO_LIST_COMMANDS = frozenset(
    {"/场景列表", "/场景 list", "/scenarios", "场景列表", "我的场景"}
)
_MY_TASKS_COMMANDS = frozenset({"/tasks", "/任务", "/我的任务", "我的任务"})
_CANCEL_TASK_COMMANDS = frozenset({"/取消任务", "/取消", "/cancel"})

# Feishu interactive-card streaming: throttle cadence and size limits.
# lark_md in cards renders most markdown but not tables; very long answers
# overflow the card, so they fall back to a plain text message.
_FEISHU_CARD_UPDATE_INTERVAL_SECONDS = 1.5
_FEISHU_CARD_MAX_CHARS = 3500

# DingTalk AI-card streaming (same protocol family as the official CLI):
# the card platform throttles rapid frames (~800ms floor) and races
# back-to-back deliver/content/finalize frames, so frames keep a gap; the
# card holds 20000 chars and overflow goes out as plain text messages.
_DINGTALK_CARD_UPDATE_INTERVAL_SECONDS = 1.5
_DINGTALK_CARD_FRAME_GAP_SECONDS = 0.5
_DINGTALK_CARD_MAX_CHARS = 20000
# flowStatus states of the AI-card template contract.
_DINGTALK_FLOW_INPUTING = "2"
_DINGTALK_FLOW_FINISHED = "3"
_DINGTALK_FLOW_FAILED = "5"

# DingTalk has no click-to-send menu primitive; every reply advertises the
# command aliases instead (the same labels the WeCom menu and the Feishu
# floating menu send as messages).
_DINGTALK_COMMAND_HINT = (
    "\n\n---\n🆕 新对话 · 📋 场景列表 · 🧰 技能 · ❓ 帮助（回复文字即可）"
)


class CallbackRejected(Exception):
    """Verification refused the callback; router answers 403."""


@dataclass(frozen=True)
class InboundAttachment:
    """One attachment carried by an inbound Feishu message, before it is
    downloaded and stored in Onyx's file store."""

    kind: str  # image | file
    message_key: str  # image_key / file_key for the download API
    file_name: str = ""
    message_id: str = ""  # containing message — resources API needs it


@dataclass(frozen=True)
class InboundMessage:
    platform: str  # wecom | dingtalk | feishu
    msg_id: str
    platform_user_id: str
    chat_id: str  # group or DM conversation id
    text: str
    sender_name: str = ""
    attachments: tuple[InboundAttachment, ...] = ()
    is_group: bool = False  # group chat → retrieval downgrades to public docs


@dataclass(frozen=True)
class _PreparedTurn:
    """Everything the chat engine needs after binding/scenario handling."""

    user_id: Any
    request: Any  # SendMessageRequest


# ── user binding (platform identity ↔ onyx user) ──────────────────────────


def upsert_im_binding(
    db_session: Session,
    *,
    user_id: Any,
    platform: str,
    platform_user_id: str,
    chat_id: str,
    display_name: str = "",
) -> None:
    from onyx.db.models import ChinaIMBinding

    row = db_session.scalar(
        select(ChinaIMBinding).where(
            ChinaIMBinding.platform == platform,
            ChinaIMBinding.platform_user_id == platform_user_id,
        )
    )
    if row is None:
        db_session.add(
            ChinaIMBinding(
                id=uuid4(),
                user_id=user_id,
                platform=platform,
                platform_user_id=platform_user_id,
                chat_id=chat_id,
                display_name=display_name,
            )
        )
    else:
        # user_id follows the resolved identity: a later SSO login rebinds
        # the chat from the shadow bot account to the human's account.
        row.user_id = user_id
        row.chat_id = chat_id
        if display_name:
            row.display_name = display_name
    db_session.commit()


def binding_for_user(db_session: Session, user_id: Any) -> Any | None:
    from onyx.db.models import ChinaIMBinding

    return db_session.scalar(
        select(ChinaIMBinding)
        .where(ChinaIMBinding.user_id == user_id)
        .order_by(ChinaIMBinding.updated_at.desc())
        .limit(1)
    )


# ── dedup ─────────────────────────────────────────────────────────────────


def seen_before(platform: str, msg_id: str, *, ttl_seconds: int = 300) -> bool:
    """Redis SETNX dedup; platforms retry callbacks on slow replies."""
    try:
        from onyx.redis.redis_pool import get_redis_client
        from shared_configs.contextvars import get_current_tenant_id

        client = get_redis_client(tenant_id=get_current_tenant_id())
        key = f"china_bot:seen:{platform}:{msg_id}"
        return not client.set(key, "1", ex=ttl_seconds, nx=True)
    except Exception:
        # Redis down: rather than double-answering every retry, drop the
        # callback entirely — the next user message re-triggers.
        logger.warning("china bot dedup unavailable; dropping callback")
        return True


# ── chat dispatch ─────────────────────────────────────────────────────────


def answer_message_async(message: InboundMessage, provider_config: Any) -> None:
    """Run the answer in a daemon thread; never blocks the callback."""
    thread = threading.Thread(
        target=_answer_safely, args=(message, provider_config), daemon=True
    )
    thread.start()


def _answer_safely(message: InboundMessage, provider_config: Any) -> None:
    if not _answer_semaphore.acquire(blocking=False):
        logger.warning("china bot answer pool saturated; dropping %s", message.msg_id)
        return
    try:
        if message.platform == "feishu":
            # Feishu answers stream into an interactive card the user can
            # watch grow; other platforms get one final message.
            _answer_feishu(message, provider_config)
        elif message.platform == "dingtalk":
            # DingTalk mirrors the Feishu experience when the provider row
            # carries an AI-card template id; plain single message otherwise.
            _answer_dingtalk(message, provider_config)
        else:
            reply = _answer(message, provider_config)
            if reply:
                _send_reply(message, provider_config, reply)
    except Exception:
        logger.exception("china bot answer failed for %s", message.msg_id)
    finally:
        _answer_semaphore.release()


def _latest_session_id(db_session: Session, user_id: Any) -> UUID | None:
    """Most recent non-deleted chat session of the bot user — the IM chat is
    one continuing conversation, so turns reuse it for context."""
    from onyx.db.models import ChatSession

    return db_session.scalar(
        select(ChatSession.id)
        .where(
            ChatSession.user_id == user_id,
            ChatSession.deleted == False,  # noqa: E712
        )
        .order_by(ChatSession.time_updated.desc())
        .limit(1)
    )


def _reset_flag_key(platform: str, platform_user_id: str) -> str:
    return f"china_bot:reset:{platform}:{platform_user_id}"


def _mark_reset(platform: str, platform_user_id: str) -> bool:
    try:
        from onyx.redis.redis_pool import get_redis_client
        from shared_configs.contextvars import get_current_tenant_id

        client = get_redis_client(tenant_id=get_current_tenant_id())
        return bool(
            client.set(
                _reset_flag_key(platform, platform_user_id),
                "1",
                ex=_RESET_FLAG_TTL_SECONDS,
            )
        )
    except Exception:
        logger.warning("china bot reset flag unavailable", exc_info=True)
        return False


def _consume_reset_flag(platform: str, platform_user_id: str) -> bool:
    try:
        from onyx.redis.redis_pool import get_redis_client
        from shared_configs.contextvars import get_current_tenant_id

        client = get_redis_client(tenant_id=get_current_tenant_id())
        key = _reset_flag_key(platform, platform_user_id)
        if client.get(key):
            client.delete(key)
            return True
    except Exception:
        logger.warning("china bot reset flag check failed", exc_info=True)
    return False


def _prepare_turn(message: InboundMessage, provider_config: Any) -> _PreparedTurn | str:
    """Provision the user, record the binding, and build the chat request.

    Returns a direct reply string for commands (`/reset`) and scenario
    triggers that bypass the chat turn."""
    from onyx.db.engine.sql_engine import get_session_with_current_tenant
    from onyx.db.users import get_user_by_email
    from onyx.onyxbot.china.scenario_trigger import try_scenario_trigger
    from onyx.server.query_and_chat.models import (
        ChatSessionCreationRequest,
        MessageOrigin,
        SendMessageRequest,
    )

    email = deterministic_email(
        message.platform, message.platform_user_id, provider_config
    )
    command = message.text.strip().lower()
    with get_session_with_current_tenant() as db_session:
        # Prefer the human's SSO-linked account; the deterministic bot
        # account is the fallback for users who never logged in via SSO.
        user = _resolve_onyx_user(db_session, message, provider_config)
        if user is None:
            user = get_user_by_email(email, db_session)
            if user is None:
                user = _provision_bot_user(db_session, email)

        # Group chats: the chat turn runs as a per-group shared account with
        # no ACL grants, so retrieval is limited to public documents — answers
        # derived from one member's private docs must not reach the group.
        # Commands and scenario launches below still run as the sender.
        if message.is_group:
            group_email = _group_account_email(message, provider_config)
            turn_user = get_user_by_email(group_email, db_session)
            if turn_user is None:
                turn_user = _provision_bot_user(db_session, group_email)
        else:
            turn_user = user
            upsert_im_binding(
                db_session,
                user_id=user.id,
                platform=message.platform,
                platform_user_id=message.platform_user_id,
                chat_id=message.chat_id,
                display_name=message.sender_name,
            )

        if command in _RESET_COMMANDS:
            _mark_reset(message.platform, message.platform_user_id)
            return "好的,已重置对话。下一条消息将开启全新的会话。"

        if command in _HELP_COMMANDS:
            return _help_reply()

        if command in _SCENARIO_LIST_COMMANDS:
            return _scenario_list_reply(db_session, user)

        if command in _MY_TASKS_COMMANDS:
            return _my_tasks_reply(db_session, user)

        # /取消任务 carries an index argument, so match by prefix
        if command in _CANCEL_TASK_COMMANDS or command.startswith(
            tuple(prefix + " " for prefix in _CANCEL_TASK_COMMANDS)
        ):
            return _cancel_task_reply(db_session, user, message.text)

        # Skill command: /技能 [关键词|序号], or the bare menu label
        # (WeCom's chat menu and DingTalk's hint line send the same label).
        if (
            command == "技能"
            or command.startswith("/技能")
            or command.startswith("/skill")
        ):
            return _skills_command_reply(
                db_session,
                user,
                message.text,
                message.platform,
                message.platform_user_id,
            )

        # Inbound Feishu attachments: download and park for the next text.
        # A post message carries text too — park its images and fall through
        # so text + attachments are consumed by the same turn.
        if message.attachments and message.platform == "feishu":
            ack = _collect_feishu_attachments(
                db_session, user, message, provider_config
            )
            if ack is not None and not message.text.strip():
                return ack

        start_fresh = _consume_reset_flag(message.platform, message.platform_user_id)
        if start_fresh:
            _clear_pending_files(message.platform, message.platform_user_id)
            _clear_pending_skill(message.platform, message.platform_user_id)
        # Session continuity is per turn-user: the member's own session in
        # DMs, the shared per-group session in group chats.
        session_id = (
            None if start_fresh else _latest_session_id(db_session, turn_user.id)
        )

        trigger_reply = try_scenario_trigger(db_session, user, message.text)
        if trigger_reply is not None:
            # parked attachments are kept for the next chat message; tell the
            # user where they went instead of silently dropping them
            pending = _read_pending_files(message.platform, message.platform_user_id)
            if pending:
                names = ", ".join(str(f.get("name") or "附件") for f in pending[:5])
                trigger_reply = (
                    f"{trigger_reply}\n\n📎 随消息的 {len(pending)} 个附件已存入你的"
                    f"文件空间({names});场景任务暂不读取附件,可在网页端会话中引用。"
                )
            return trigger_reply

        file_descriptors: list[dict[str, Any]] = []
        if message.platform == "feishu" and not message.is_group:
            # Parked files are owned by the sender; group turns run as the
            # shared group account, which would fail the ownership check.
            file_descriptors = _consume_pending_files(
                message.platform, message.platform_user_id
            )
        selected_skill_ids = None
        if message.platform == "feishu":
            selected_skill_ids = (
                None
                if start_fresh
                else _consume_pending_skill(message.platform, message.platform_user_id)
            )
            if selected_skill_ids:
                selected_skill_ids = [selected_skill_ids]

    origin_value = {
        "wecom": MessageOrigin.WECOMBOT,
        "dingtalk": MessageOrigin.DINGTALKBOT,
        "feishu": MessageOrigin.FEISHUBOT,
    }[message.platform]

    request = SendMessageRequest(
        message=message.text,
        origin=origin_value,
        # Continue the ongoing conversation when there is one. When starting
        # fresh, pass the creation request explicitly — SendMessageRequest's
        # after-validator that defaults it is a no-op under __init__
        # (pydantic v2 ignores non-self returns there).
        chat_session_id=session_id,
        chat_session_info=None if session_id else ChatSessionCreationRequest(),
        file_descriptors=file_descriptors,
        selected_skill_ids=selected_skill_ids,
    )
    return _PreparedTurn(user_id=turn_user.id, request=request)


def _iter_chat_stream(prepared: _PreparedTurn) -> Any:
    """Open the chat-engine stream for one turn; hold the DB session open
    for as long as the caller consumes the generator."""
    from onyx.chat.process_message import handle_stream_message_objects
    from onyx.db.engine.sql_engine import get_session_with_current_tenant
    from onyx.db.models import User

    with get_session_with_current_tenant() as db_session:
        fresh_user = db_session.scalar(
            select(User).where(
                User.id == prepared.user_id  # ty: ignore[invalid-argument-type]
            )
        )
        assert fresh_user is not None
        yield from handle_stream_message_objects(
            prepared.request, fresh_user, bypass_acl=False
        )


def _answer(message: InboundMessage, provider_config: Any) -> str | None:
    """Provision the user and run one in-process chat turn to completion.

    ``/场景`` commands bypass the chat turn and start a CraftJob instead."""
    from onyx.chat.process_message import gather_stream

    prepared = _prepare_turn(message, provider_config)
    if isinstance(prepared, str):
        return prepared
    response = gather_stream(_iter_chat_stream(prepared))
    if response is None:
        return None
    return response.answer.strip() or None


# ── feishu streaming card answer ──────────────────────────────────────────


def _answer_feishu(message: InboundMessage, provider_config: Any) -> None:
    """Answer a Feishu message, streaming progress into an interactive card.

    Falls back to the plain gather-then-send path when the card cannot be
    created (older bots, API errors)."""
    from onyx.chat.models import StreamingError
    from onyx.connectors.china_common import AppTokenManager
    from onyx.server.query_and_chat.streaming_models import AgentResponseDelta, Packet

    token_mgr = AppTokenManager
    prepared = _prepare_turn(message, provider_config)
    if isinstance(prepared, str):
        # Direct replies (menu commands, /场景 launches) carry markdown too —
        # send them as cards, not plain text.
        _feishu_reply_rich(provider_config, token_mgr, message.chat_id, prepared)
        return

    card_msg_id = _feishu_send_card(
        provider_config, token_mgr, message.chat_id, "🤔 正在思考…"
    )
    if card_msg_id is None:
        # No card support — behave like the other platforms.
        reply = _answer_from_prepared(prepared)
        if reply:
            _feishu_send(provider_config, token_mgr, message.chat_id, reply)
        return

    answer = ""
    error_msg: str | None = None
    last_update = time.monotonic()
    try:
        for packet in _iter_chat_stream(prepared):
            if isinstance(packet, StreamingError):
                error_msg = packet.error
                break
            if not isinstance(packet, Packet):
                continue
            if isinstance(packet.obj, AgentResponseDelta) and packet.obj.content:
                answer += packet.obj.content
                now = time.monotonic()
                if now - last_update >= _FEISHU_CARD_UPDATE_INTERVAL_SECONDS:
                    _feishu_update_card(provider_config, token_mgr, card_msg_id, answer)
                    last_update = now
    except Exception:
        logger.exception("feishu streaming answer failed for %s", message.msg_id)
        error_msg = error_msg or "处理过程中出现错误"

    if not answer.strip() and not error_msg:
        error_msg = "未生成回答"

    if error_msg:
        detail = f"⚠️ 回答失败:{error_msg}"[:_FEISHU_CARD_MAX_CHARS]
        _feishu_update_card(provider_config, token_mgr, card_msg_id, detail)
        return

    display = answer.strip()
    chunks = _split_for_cards(display, _FEISHU_CARD_MAX_CHARS)
    # First chunk updates the streaming card in place; extra chunks go out
    # as their own cards so every page renders markdown (no raw-text DMs).
    _feishu_update_card(provider_config, token_mgr, card_msg_id, chunks[0])
    total = len(chunks)
    for i, chunk in enumerate(chunks[1:], start=2):
        part = f"**({i}/{total})**\n\n{chunk}"
        if _feishu_send_card(provider_config, token_mgr, message.chat_id, part) is None:
            _feishu_send(provider_config, token_mgr, message.chat_id, chunk)


def _split_for_cards(text: str, limit: int) -> list[str]:
    """Split long text into card-sized chunks at paragraph or line
    boundaries; a single oversized paragraph is hard-cut."""
    chunks: list[str] = []
    rest = text.strip()
    while len(rest) > limit:
        cut = rest.rfind("\n\n", 0, limit)
        if cut < limit // 2:
            cut = rest.rfind("\n", 0, limit)
        if cut < limit // 2:
            cut = limit
        chunks.append(rest[:cut].rstrip())
        rest = rest[cut:].lstrip("\n")
    if rest:
        chunks.append(rest)
    return chunks or [text]


# ── dingtalk AI-card streaming answer ─────────────────────────────────────


def _answer_dingtalk(message: InboundMessage, provider_config: Any) -> None:
    """Answer a DingTalk message, streaming progress into an AI card when the
    provider row carries ``bot_card_template_id``; a single plain message
    otherwise. Group chats reply in the group either way."""
    from onyx.chat.models import StreamingError
    from onyx.connectors.china_common import AppTokenManager
    from onyx.server.query_and_chat.streaming_models import AgentResponseDelta, Packet

    token_mgr = AppTokenManager
    prepared = _prepare_turn(message, provider_config)
    if isinstance(prepared, str):
        # Direct replies (menu commands, /场景 launches) ride a card too.
        _dingtalk_reply_rich(message, provider_config, token_mgr, prepared)
        return

    card_id = _dingtalk_card_start(message, provider_config, token_mgr)
    if card_id is None:
        # No card support — behave like the other plain-text platforms.
        reply = _answer_from_prepared(prepared)
        if reply:
            _dingtalk_send(
                provider_config,
                token_mgr,
                message.chat_id,
                message.platform_user_id,
                reply,
                is_group=message.is_group,
            )
        return

    answer = ""
    error_msg: str | None = None
    last_update = time.monotonic()
    try:
        for packet in _iter_chat_stream(prepared):
            if isinstance(packet, StreamingError):
                error_msg = packet.error
                break
            if not isinstance(packet, Packet):
                continue
            if isinstance(packet.obj, AgentResponseDelta) and packet.obj.content:
                answer += packet.obj.content
                now = time.monotonic()
                if now - last_update >= _DINGTALK_CARD_UPDATE_INTERVAL_SECONDS:
                    _dingtalk_card_set_flow(
                        provider_config,
                        token_mgr,
                        card_id,
                        _DINGTALK_FLOW_INPUTING,
                        answer,
                    )
                    last_update = time.monotonic()
    except Exception:
        logger.exception("dingtalk streaming answer failed for %s", message.msg_id)
        error_msg = error_msg or "处理过程中出现错误"

    if not answer.strip() and not error_msg:
        error_msg = "未生成回答"

    if error_msg:
        detail = f"⚠️ 回答失败:{error_msg}"
        _dingtalk_card_set_flow(
            provider_config, token_mgr, card_id, _DINGTALK_FLOW_FAILED, detail
        )
        return

    display = answer.strip()
    # The card holds the first chunk; overflow beyond its capacity goes out
    # as follow-up plain-text messages.
    _dingtalk_card_finish(
        provider_config, token_mgr, card_id, display[:_DINGTALK_CARD_MAX_CHARS]
    )
    overflow = display[_DINGTALK_CARD_MAX_CHARS:]
    if overflow:
        for chunk in _split_for_cards(overflow, _DINGTALK_CARD_MAX_CHARS):
            _dingtalk_send(
                provider_config,
                token_mgr,
                message.chat_id,
                message.platform_user_id,
                chunk,
                is_group=message.is_group,
            )


def _dingtalk_reply_rich(
    message: InboundMessage, config: Any, token_mgr: Any, text: str
) -> None:
    """Reply to a command-style message through the AI card when configured,
    falling back to a plain text send."""
    card_id = _dingtalk_card_start(message, config, token_mgr)
    if card_id is None:
        _dingtalk_send(
            config,
            token_mgr,
            message.chat_id,
            message.platform_user_id,
            text,
            is_group=message.is_group,
        )
        return
    _dingtalk_card_finish(config, token_mgr, card_id, text)


def _dingtalk_robot_code(config: Any) -> str:
    # Robot code defaults to the AppKey for enterprise internal apps.
    return str(config.robot_code or config.client_id)


def _dingtalk_card_api(
    config: Any, token_mgr: Any, method: str, path: str, payload: dict[str, Any]
) -> None:
    """One authenticated card-API request. The deliver endpoint reports
    per-target failures INSIDE a HTTP 200 (`{"success": false, ...}`), so
    both layers are checked."""
    import requests

    token = _dingtalk_token(config, token_mgr)
    resp = requests.request(
        method,
        f"https://api.dingtalk.com{path}",
        headers={
            "x-acs-dingtalk-access-token": token,
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=15,
    )
    resp.raise_for_status()
    try:
        body = resp.json()
    except ValueError:
        return
    if isinstance(body, dict) and body.get("success") is False:
        raise RuntimeError(f"card API business failure: {str(body)[:200]}")


def _dingtalk_card_start(
    message: InboundMessage, config: Any, token_mgr: Any
) -> str | None:
    """Create + deliver a streaming AI card into the conversation the message
    came from. Returns the outTrackId, or None (any failure → the caller
    falls back to plain text)."""
    template_id = config.bot_card_template_id
    if not template_id:
        return None
    try:
        out_track_id = f"onyx_{uuid4()}"
        _dingtalk_card_api(
            config,
            token_mgr,
            "POST",
            "/v1.0/card/instances",
            {
                "cardTemplateId": template_id,
                "outTrackId": out_track_id,
                "cardData": {"cardParamMap": {"config": '{"autoLayout":true}'}},
                "callbackType": "STREAM",
                "imGroupOpenSpaceModel": {"supportForward": True},
                "imRobotOpenSpaceModel": {"supportForward": True},
            },
        )
        deliver: dict[str, Any] = {"outTrackId": out_track_id, "userIdType": 1}
        if message.is_group:
            deliver["openSpaceId"] = f"dtv1.card//IM_GROUP.{message.chat_id}"
            deliver["imGroupOpenDeliverModel"] = {
                "robotCode": _dingtalk_robot_code(config)
            }
        else:
            deliver["openSpaceId"] = f"dtv1.card//IM_ROBOT.{message.platform_user_id}"
            deliver["imRobotOpenDeliverModel"] = {
                "spaceType": "IM_ROBOT",
                "robotCode": _dingtalk_robot_code(config),
                "extension": {"dynamicSummary": "true"},
            }
        _dingtalk_card_api(
            config, token_mgr, "POST", "/v1.0/card/instances/deliver", deliver
        )
        # Back-to-back deliver → content → finalize frames race the client's
        # card fetch and intermittently render "内容加载失败".
        time.sleep(_DINGTALK_CARD_FRAME_GAP_SECONDS)
        return out_track_id
    except Exception:
        logger.warning(
            "dingtalk card start failed; falling back to text", exc_info=True
        )
        return None


def _dingtalk_card_params(flow_status: str, content: str) -> dict[str, str]:
    """The cardParamMap contract of the AI-card template (msgContent carries
    the markdown the streaming frames write into)."""
    return {
        "flowStatus": flow_status,
        "msgContent": content,
        "staticMsgContent": "",
        "sys_full_json_obj": '{"order":["msgContent"]}',
        "config": '{"autoLayout":true}',
    }


def _dingtalk_card_set_flow(
    config: Any, token_mgr: Any, out_track_id: str, flow_status: str, content: str
) -> None:
    """Update the card instance's flow state (and content); failures are
    logged, never raised — a missed intermediate update must not kill the
    answer."""
    try:
        _dingtalk_card_api(
            config,
            token_mgr,
            "PUT",
            "/v1.0/card/instances",
            {
                "outTrackId": out_track_id,
                "cardData": {
                    "cardParamMap": _dingtalk_card_params(flow_status, content)
                },
                "cardUpdateOptions": {"updateCardDataByKey": True},
            },
        )
    except Exception:
        logger.warning(
            "dingtalk card flow update failed for %s", out_track_id, exc_info=True
        )


def _dingtalk_card_finish(
    config: Any, token_mgr: Any, out_track_id: str, content: str
) -> None:
    """Close the card: the finalized streaming frame plus the FINISHED flow
    state, with the frame gap the client needs between the two."""
    try:
        content = content + _DINGTALK_COMMAND_HINT if content.strip() else content
        _dingtalk_card_api(
            config,
            token_mgr,
            "PUT",
            "/v1.0/card/streaming",
            {
                "outTrackId": out_track_id,
                "guid": str(uuid4()),
                "key": "msgContent",
                "content": content[:_DINGTALK_CARD_MAX_CHARS],
                "isFull": True,
                "isFinalize": True,
                "isError": False,
            },
        )
        time.sleep(_DINGTALK_CARD_FRAME_GAP_SECONDS)
        _dingtalk_card_set_flow(
            config, token_mgr, out_track_id, _DINGTALK_FLOW_FINISHED, content
        )
    except Exception:
        logger.warning(
            "dingtalk card finish failed for %s", out_track_id, exc_info=True
        )


def _answer_from_prepared(prepared: _PreparedTurn) -> str | None:
    from onyx.chat.process_message import gather_stream

    response = gather_stream(_iter_chat_stream(prepared))
    if response is None:
        return None
    return response.answer.strip() or None


def _provision_bot_user(db_session: Session, email: str) -> Any:
    """BOT account for the IM user (same convention as the Slack bot)."""
    from onyx.db.enums import AccountType
    from onyx.db.models import User
    from onyx.db.users import _generate_password_hash

    user = User(
        email=email,
        hashed_password=_generate_password_hash(),
        account_type=AccountType.BOT,
    )
    db_session.add(user)
    db_session.commit()
    return user


def deterministic_email(platform: str, platform_user_id: str, config: Any) -> str:
    # Every provider config model (and test stub) carries email_domain.
    domain = config.email_domain or BOT_EMAIL_DOMAIN_FALLBACK
    return f"{platform}-{platform_user_id}@{domain}"


def _group_account_email(message: InboundMessage, config: Any) -> str:
    """Deterministic per-group shared account: no ACL grants, so group chat
    retrieval is limited to public documents; memories and sessions stay
    scoped to this one group and cannot leak across groups."""
    domain = config.email_domain or BOT_EMAIL_DOMAIN_FALLBACK
    return f"{message.platform}-group-{message.chat_id}@{domain}"


# ── real-identity resolution (open_id → union_id → SSO-linked user) ───────

# open_id → union_id is stable per app; cache per process to spare the
# contact API one call per message.
_UNION_ID_CACHE: dict[tuple[str, str], str | None] = {}


def _feishu_union_id(config: Any, token_mgr: Any, open_id: str) -> str | None:
    cache_key = (config.app_id, open_id)
    if cache_key in _UNION_ID_CACHE:
        return _UNION_ID_CACHE[cache_key]
    union_id: str | None = None
    try:
        import requests

        token = _feishu_token(config, token_mgr)
        # single-user GET: the batch_get path routes to /users/{id} here and
        # mis-parses "batch_get" as a user id
        resp = requests.get(
            f"https://open.feishu.cn/open-apis/contact/v3/users/{open_id}",
            params={"user_id_type": "open_id"},
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        user = (resp.json().get("data") or {}).get("user") or {}
        union_id = user.get("union_id") or None
    except Exception:
        logger.warning("feishu union_id lookup failed for %s", open_id)
    _UNION_ID_CACHE[cache_key] = union_id
    return union_id


def _resolve_onyx_user(
    db_session: Session, message: InboundMessage, provider_config: Any
) -> Any | None:
    """The human's Onyx identity when their Feishu account is SSO-linked:
    open_id → union_id → oauth_account(``feishu:{app_id}:{union_id}``).

    Running the turn as that user keeps scenario/skill visibility and
    document ACLs aligned with what the human sees on the web. Returns
    None when unresolvable (no SSO linkage, contact API down) so the
    caller falls back to the deterministic bot account."""
    if message.platform != "feishu":
        return None
    from onyx.connectors.china_common import AppTokenManager
    from onyx.db.models import OAuthAccount, User

    union_id = _feishu_union_id(
        provider_config, AppTokenManager, message.platform_user_id
    )
    if not union_id:
        return None
    account_id = f"feishu:{provider_config.app_id}:{union_id}"
    return db_session.scalar(
        select(User)
        .join(
            OAuthAccount,
            OAuthAccount.user_id == User.id,  # ty: ignore[invalid-argument-type]
        )
        .where(
            OAuthAccount.oauth_name == "feishu",  # ty: ignore[invalid-argument-type]
            OAuthAccount.account_id == account_id,  # ty: ignore[invalid-argument-type]
            User.is_active == True,  # noqa: E712  # ty: ignore[invalid-argument-type]
        )
        .limit(1)
    )


# ── pending attachments (Feishu images/files → Onyx chat files) ──────────

_PENDING_FILES_PREFIX = "china_bot:files:"
_PENDING_FILES_TTL_SECONDS = 24 * 3600
_MAX_PENDING_FILES = 10

# pending skill selection: applied to the next chat message
_SKILL_FLAG_PREFIX = "china_bot:skill:"
_SKILL_FLAG_TTL_SECONDS = 30 * 60


def _pending_files_key(platform: str, platform_user_id: str) -> str:
    return f"{_PENDING_FILES_PREFIX}{platform}:{platform_user_id}"


def _read_pending_files(platform: str, platform_user_id: str) -> list[dict[str, Any]]:
    try:
        from onyx.redis.redis_pool import get_redis_client
        from shared_configs.contextvars import get_current_tenant_id

        client = get_redis_client(tenant_id=get_current_tenant_id())
        raw = client.get(_pending_files_key(platform, platform_user_id))
        files = json.loads(raw) if raw else []
        return files if isinstance(files, list) else []
    except Exception:
        logger.warning("pending file list read failed", exc_info=True)
        return []


def _write_pending_files(
    platform: str, platform_user_id: str, files: list[dict[str, Any]]
) -> None:
    try:
        from onyx.redis.redis_pool import get_redis_client
        from shared_configs.contextvars import get_current_tenant_id

        client = get_redis_client(tenant_id=get_current_tenant_id())
        client.set(
            _pending_files_key(platform, platform_user_id),
            json.dumps(files, ensure_ascii=False),
            ex=_PENDING_FILES_TTL_SECONDS,
        )
    except Exception:
        logger.warning("pending file list write failed", exc_info=True)


def _clear_pending_files(platform: str, platform_user_id: str) -> None:
    try:
        from onyx.redis.redis_pool import get_redis_client
        from shared_configs.contextvars import get_current_tenant_id

        client = get_redis_client(tenant_id=get_current_tenant_id())
        client.delete(_pending_files_key(platform, platform_user_id))
    except Exception:
        logger.warning("pending file list clear failed", exc_info=True)


def _feishu_download(
    config: Any, token_mgr: Any, attachment: InboundAttachment
) -> tuple[bytes, str] | None:
    """Download one inbound attachment via the message-resources API.

    ``/im/v1/files|images/{key}`` only serves resources the bot uploaded
    itself; user-sent attachments hang off their message and must go
    through ``/im/v1/messages/{message_id}/resources/{key}``."""
    import requests

    token = _feishu_token(config, token_mgr)
    resource_type = "image" if attachment.kind == "image" else "file"
    resp = requests.get(
        (
            f"https://open.feishu.cn/open-apis/im/v1/messages/"
            f"{attachment.message_id}/resources/{attachment.message_key}"
        ),
        params={"type": resource_type},
        headers={"Authorization": f"Bearer {token}"},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.content, (resp.headers.get("Content-Type") or "").split(";")[0]


def _store_feishu_attachment(
    db_session: Session,
    user: Any,
    config: Any,
    token_mgr: Any,
    attachment: InboundAttachment,
) -> tuple[dict[str, Any], str] | str:
    """Download + store one attachment as the user's Onyx file.

    Returns ``(file_descriptor, display_name)`` on success or an error
    message string on rejection."""
    import mimetypes

    from onyx.configs.app_configs import DEFAULT_USER_FILE_MAX_UPLOAD_SIZE_MB
    from onyx.db.enums import UserFileStatus
    from onyx.db.models import UserFile
    from onyx.file_processing.file_types import OnyxMimeTypes
    from onyx.file_store.file_store import get_default_file_store
    from onyx.server.query_and_chat.chat_utils import mime_type_to_chat_file_type

    try:
        downloaded = _feishu_download(config, token_mgr, attachment)
    except Exception:
        logger.exception("feishu attachment download failed")
        return f"❌ {attachment.file_name or attachment.kind} 下载失败,请重试"
    if downloaded is None:
        return f"❌ {attachment.file_name or attachment.kind} 下载失败"
    content, content_mime = downloaded

    name = attachment.file_name or (
        f"feishu-image.{content_mime.split('/')[-1] or 'png'}"
        if attachment.kind == "image"
        else "feishu-file"
    )
    mime = mimetypes.guess_type(name)[0] or (
        content_mime if content_mime else "application/octet-stream"
    )

    max_bytes = DEFAULT_USER_FILE_MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if len(content) > max_bytes:
        return (
            f"❌ {name} 超过大小上限({DEFAULT_USER_FILE_MAX_UPLOAD_SIZE_MB}MB),已跳过"
        )
    normalized = mime.lower()
    if normalized not in OnyxMimeTypes.ALLOWED_MIME_TYPES and (
        f"{normalized.split('/')[0]}/*" not in OnyxMimeTypes.ALLOWED_MIME_TYPES
    ):
        return f"❌ {name}:暂不支持该文件类型({mime})"

    descriptor_type = mime_type_to_chat_file_type(mime)
    file_id = get_default_file_store().save_file(
        io.BytesIO(content),
        display_name=name,
        file_origin=FileOrigin.USER_FILE,
        file_type=mime,
    )
    user_file = UserFile(
        id=uuid4(),
        user_id=user.id,
        file_id=file_id,
        name=name,
        token_count=max(1, len(content) // 4),
        content_type=mime,
        file_type=mime,
        status=UserFileStatus.SKIPPED,
        last_accessed_at=datetime.datetime.now(datetime.timezone.utc),
    )
    db_session.add(user_file)
    db_session.commit()
    descriptor = {
        "id": file_id,
        "type": descriptor_type.value,
        "name": name,
        "user_file_id": str(user_file.id),
    }
    return descriptor, name


def _help_reply() -> str:
    return (
        "🤖 **Onyx 机器人使用指南**\n"
        "- 直接发消息即可提问:回答会检索已接入的知识库(如飞书知识库)并按需联网\n"
        "- **附件**:先发图片/文件(可多个),再发文字说明即可一并处理\n"
        "- **/技能** 或 /技能 <关键词>:查看/搜索技能,/技能 <序号> 选中后下一条消息携带技能执行\n"
        "- **/场景** <名称> <任务内容>:启动自动化场景任务\n"
        "- **/场景列表**:查看当前可用的场景\n"
        "- **/我的任务**:查看运行中的场景任务(每人同时最多有限额内的任务)\n"
        "- **/取消任务** <序号>:取消一个运行中的任务并释放额度\n"
        "- **/reset**:开启新对话(清除上下文、待用附件与技能)\n"
        "- **/帮助**:显示本指南"
    )


def _collect_feishu_attachments(
    db_session: Session,
    user: Any,
    message: InboundMessage,
    provider_config: Any,
) -> str | None:
    """Download and park inbound attachments for the next chat message.

    Returns an ack/error reply; ``None`` when everything is already at the
    per-user pending cap."""
    from onyx.connectors.china_common import AppTokenManager

    token_mgr = AppTokenManager
    pending = _read_pending_files(message.platform, message.platform_user_id)
    collected: list[str] = []
    errors: list[str] = []
    for attachment in message.attachments:
        if len(pending) >= _MAX_PENDING_FILES:
            errors.append(
                f"❌ {attachment.file_name or attachment.kind}:待处理附件已满({_MAX_PENDING_FILES} 个),先发送文字消息处理它们"
            )
            continue
        result = _store_feishu_attachment(
            db_session, user, provider_config, token_mgr, attachment
        )
        if isinstance(result, str):
            errors.append(result)
            continue
        descriptor, display_name = result
        pending.append(descriptor)
        collected.append(display_name)
    _write_pending_files(message.platform, message.platform_user_id, pending)

    parts = []
    if collected:
        parts.append(
            f"📎 已收到:{'、'.join(collected)}(待处理 {len(pending)}/{_MAX_PENDING_FILES})。"
            "补充文字说明后发送,即可连同附件一起处理。"
        )
    if errors:
        parts.append("\n".join(errors))
    return "\n".join(parts) if parts else None


def _consume_pending_files(
    platform: str, platform_user_id: str
) -> list[dict[str, Any]]:
    files = _read_pending_files(platform, platform_user_id)
    if files:
        _clear_pending_files(platform, platform_user_id)
    return files


# ── pending skill selection ───────────────────────────────────────────────


def _skill_flag_key(platform: str, platform_user_id: str) -> str:
    return f"{_SKILL_FLAG_PREFIX}{platform}:{platform_user_id}"


def _consume_pending_skill(platform: str, platform_user_id: str) -> str | None:
    try:
        from onyx.redis.redis_pool import get_redis_client
        from shared_configs.contextvars import get_current_tenant_id

        client = get_redis_client(tenant_id=get_current_tenant_id())
        key = _skill_flag_key(platform, platform_user_id)
        raw = client.get(key)
        if raw:
            client.delete(key)
            return raw if isinstance(raw, str) else raw.decode("utf-8")
    except Exception:
        logger.warning("pending skill read failed", exc_info=True)
    return None


def _clear_pending_skill(platform: str, platform_user_id: str) -> None:
    try:
        from onyx.redis.redis_pool import get_redis_client
        from shared_configs.contextvars import get_current_tenant_id

        client = get_redis_client(tenant_id=get_current_tenant_id())
        client.delete(_skill_flag_key(platform, platform_user_id))
    except Exception:
        logger.warning("pending skill clear failed", exc_info=True)


def _first_line(text: str | None, *, fallback: str) -> str:
    """First non-empty line of a free-text field; empty fields collapse."""
    for line in (text or "").strip().splitlines():
        if line.strip():
            return line.strip()
    return fallback


def _skills_command_reply(
    db_session: Session,
    user: Any,
    text: str,
    platform: str,
    platform_user_id: str,
) -> str:
    """/技能 [关键词|序号]:list, search, or select a runtime skill."""
    from onyx.db.skill import list_runtime_skills_for_user

    skills = list_runtime_skills_for_user(db_session=db_session, user=user)
    arg = ""
    stripped = text.strip()
    for prefix in ("/技能", "/skill"):
        if stripped.startswith(prefix):
            arg = stripped[len(prefix) :].strip()
            break
    else:
        if stripped == "技能":
            arg = ""

    if not skills:
        return "🧰 当前没有可用技能。技能由管理员上传配置。"

    if arg.isdigit():
        idx = int(arg)
        if idx < 1 or idx > len(skills):
            return f"序号超出范围:当前共 {len(skills)} 个技能。见 /技能。"
        skill = sorted(skills, key=lambda s: s.updated_at, reverse=True)[idx - 1]
        try:
            from onyx.redis.redis_pool import get_redis_client
            from shared_configs.contextvars import get_current_tenant_id

            client = get_redis_client(tenant_id=get_current_tenant_id())
            client.set(
                _skill_flag_key(platform, platform_user_id),
                skill.name,
                ex=_SKILL_FLAG_TTL_SECONDS,
            )
        except Exception:
            logger.warning("pending skill write failed", exc_info=True)
            return "技能选择暂不可用,请稍后重试。"
        return (
            f"✅ 已选技能「{skill.name}」。下一条消息将携带该技能执行;"
            "发 /取消技能 取消。"
        )

    keyword = arg
    if keyword:
        lowered = keyword.lower()
        matches = [
            s
            for s in skills
            if lowered in s.name.lower() or lowered in (s.description or "").lower()
        ]
        if not matches:
            return f"未找到包含「{keyword}」的技能。发 /技能 查看全部。"
        shown = matches[:10]
        scope = f"(匹配「{keyword}」{len(matches)} 个,显示前 10)"
    else:
        shown = sorted(skills, key=lambda s: s.updated_at, reverse=True)[:10]
        scope = f"(共 {len(skills)} 个,显示最近更新)"

    lines = [
        f"{i}. **{s.name}**:{_first_line(s.description, fallback=s.name)[:60]}"
        for i, s in enumerate(shown, start=1)
    ]
    listing = "\n".join(lines)
    return (
        f"🧰 可用技能 {scope}:\n{listing}\n\n"
        "搜索:/技能 <关键词>;选择:/技能 <序号>;选中后下一条消息携带技能执行。"
    )


_CRAFT_STATUS_LABELS = {
    "pending": "排队中",
    "running": "运行中",
    "waiting_lanes": "运行中",
    "interrupted": "待处理(需在网页端确认)",
}


def _my_tasks_reply(db_session: Session, user: Any) -> str:
    from onyx.db.craft_job import list_open_craft_jobs_for_user
    from onyx.db.enums import SessionOrigin
    from onyx.onyxbot.china.scenario_trigger import craft_job_link, im_job_display_name
    from onyx.server.settings.store import load_settings

    jobs = list_open_craft_jobs_for_user(db_session, user.id, origin=SessionOrigin.IM)
    if not jobs:
        return "📭 当前没有运行中的场景任务。用 /场景 <名称> <任务内容> 启动。"
    limit = load_settings().im_craft_job_concurrency_limit
    lines = []
    for idx, job in enumerate(jobs, start=1):
        label = _CRAFT_STATUS_LABELS.get(
            str(job.status.value).lower(),
            str(job.status),
        )
        display = im_job_display_name(job.name)
        lines.append(
            f"{idx}. [{display}]({craft_job_link(job.session_id)}) — {label}"
            f"\n   sessionId: {job.session_id}"
        )
    listing = "\n".join(lines)
    return (
        f"📋 运行中的场景任务({len(jobs)}/{limit}):\n{listing}\n\n"
        "点击任务名可在浏览器打开;完成或失败会自动通知你;"
        "/取消任务 <序号> 可取消并释放额度。"
    )


def _cancel_task_reply(db_session: Session, user: Any, text: str) -> str:
    from onyx.db.craft_job import list_open_craft_jobs_for_user
    from onyx.db.enums import SessionOrigin
    from onyx.server.features.build.jobs.api import cancel_open_job_for_user

    arg = (
        text.strip().split(maxsplit=1)[1].strip()
        if len(text.strip().split(maxsplit=1)) > 1
        else ""
    )
    if not arg.isdigit():
        return "用法:/取消任务 <序号>(序号见 /我的任务 列表)"
    jobs = list_open_craft_jobs_for_user(db_session, user.id, origin=SessionOrigin.IM)
    idx = int(arg)
    if idx < 1 or idx > len(jobs):
        return f"序号超出范围:当前共 {len(jobs)} 个运行中的任务。见 /我的任务。"
    job = jobs[idx - 1]
    cancel_open_job_for_user(db_session, job, user.id)
    return f"✅ 已取消:{job.name}。额度已释放,可以启动新的任务了。"


def _scenario_list_reply(db_session: Session, user: Any) -> str:
    from onyx.db.scenario import list_scenarios_for_user

    scenarios = list_scenarios_for_user(db_session, user)
    if not scenarios:
        return "📋 当前没有可用场景。场景由管理员在广场配置。"
    lines = []
    for scenario in scenarios:
        line = f"- **{scenario.name}**"
        description = (scenario.description or "").strip()
        if description:
            line += f":{description.splitlines()[0][:60]}"
        lines.append(line)
    return (
        f"📋 可用场景({len(scenarios)}):\n"
        + "\n".join(lines)
        + "\n\n用 **/场景 <名称> <任务内容>** 启动。"
    )


# ── replies + push ────────────────────────────────────────────────────────


def _send_reply(message: InboundMessage, config: Any, text: str) -> None:
    from onyx.connectors.china_common import AppTokenManager

    if message.platform == "wecom":
        _wecom_send(config, AppTokenManager, message.chat_id, text)
    elif message.platform == "dingtalk":
        _dingtalk_send(
            config,
            AppTokenManager,
            message.chat_id,
            message.platform_user_id,
            text,
            is_group=message.is_group,
        )
    elif message.platform == "feishu":
        _feishu_reply_rich(config, AppTokenManager, message.chat_id, text)
    else:
        logger.warning("unknown platform %s", message.platform)


def _wecom_send(config: Any, token_mgr: Any, chat_id: str, text: str) -> None:
    import requests

    def fetch() -> tuple[str, int]:
        resp = requests.get(
            "https://qyapi.weixin.qq.com/cgi-bin/gettoken",
            params={"corpid": config.corp_id, "corpsecret": config.corp_secret},
            timeout=15,
        )
        data = resp.json()
        return str(data["access_token"]), int(data.get("expires_in", 7200))

    token = token_mgr(fetch).get()
    requests.post(
        "https://qyapi.weixin.qq.com/cgi-bin/message/send",
        params={"access_token": token},
        json={
            "touser": chat_id,
            "msgtype": "text",
            "agentid": int(config.agent_id),
            "text": {"content": text[:2000]},
        },
        timeout=15,
    ).raise_for_status()


# Chat-bottom menu mirroring the Feishu floating menu: every button's key is
# a command alias _prepare_turn already answers.
_WECOM_MENU_BUTTONS: list[dict[str, Any]] = [
    {
        "name": "对话",
        "sub_button": [
            {"type": "click", "name": "🆕 新对话", "key": "新对话"},
            {"type": "click", "name": "📋 我的任务", "key": "我的任务"},
        ],
    },
    {
        "name": "发现",
        "sub_button": [
            {"type": "click", "name": "📋 我的场景", "key": "我的场景"},
            {"type": "click", "name": "🧰 技能", "key": "技能"},
        ],
    },
    {"type": "click", "name": "❓ 使用帮助", "key": "使用帮助"},
]


def _wecom_menu_create(config: Any, token_mgr: Any) -> dict[str, Any]:
    """Create the app's chat-bottom custom menu (click buttons → command
    aliases). Returns the WeCom API response for errcode checking."""
    import requests

    def fetch() -> tuple[str, int]:
        resp = requests.get(
            "https://qyapi.weixin.qq.com/cgi-bin/gettoken",
            params={"corpid": config.corp_id, "corpsecret": config.corp_secret},
            timeout=15,
        )
        data = resp.json()
        return str(data["access_token"]), int(data.get("expires_in", 7200))

    token = token_mgr(fetch).get()
    resp = requests.post(
        "https://qyapi.weixin.qq.com/cgi-bin/menu/create",
        params={"access_token": token, "agentid": int(config.agent_id)},
        json={"button": _WECOM_MENU_BUTTONS},
        timeout=15,
    )
    resp.raise_for_status()
    return dict(resp.json())


def _dingtalk_token(config: Any, token_mgr: Any) -> str:
    import requests

    def fetch() -> tuple[str, int]:
        resp = requests.post(
            "https://api.dingtalk.com/v1.0/oauth2/accessToken",
            json={"appKey": config.client_id, "appSecret": config.client_secret},
            timeout=15,
        )
        data = resp.json()
        return str(data["accessToken"]), int(data.get("expireIn", 7200))

    return token_mgr(fetch).get()


def _dingtalk_send(
    config: Any,
    token_mgr: Any,
    chat_id: str,
    user_id: str,
    text: str,
    *,
    is_group: bool = False,
) -> None:
    """Reply in the conversation the message came from: group chats get a
    markdown message in the group, direct chats a robot 1:1 send."""
    import requests

    # Truncate the body so the hint always survives the platform limit.
    body_limit = max(0, 2000 - len(_DINGTALK_COMMAND_HINT))
    text = text[:body_limit] + _DINGTALK_COMMAND_HINT if text.strip() else text
    token = _dingtalk_token(config, token_mgr)
    if is_group and chat_id:
        title = text.strip().splitlines()[0][:30] if text.strip() else "Onyx"
        requests.post(
            "https://api.dingtalk.com/v1.0/robot/groupMessages/send",
            headers={"x-acs-dingtalk-access-token": token},
            json={
                "robotCode": _dingtalk_robot_code(config),
                "openConversationId": chat_id,
                "msgKey": "sampleMarkdown",
                "msgParam": json.dumps(
                    {"title": title, "text": text[:2000]}, ensure_ascii=False
                ),
            },
            timeout=15,
        ).raise_for_status()
        return
    requests.post(
        "https://api.dingtalk.com/v1.0/robot/oToMessages/batchSend",
        headers={"x-acs-dingtalk-access-token": token},
        json={
            "robotCode": _dingtalk_robot_code(config),
            "userIds": [user_id],
            "msgKey": "sampleText",
            "msgParam": json.dumps({"content": text[:2000]}, ensure_ascii=False),
        },
        timeout=15,
    ).raise_for_status()


def _feishu_token(config: Any, token_mgr: Any) -> str:
    import requests

    def fetch() -> tuple[str, int]:
        resp = requests.post(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": config.app_id, "app_secret": config.app_secret},
            timeout=15,
        )
        data = resp.json()
        return str(data["tenant_access_token"]), int(data.get("expire", 7200))

    return token_mgr(fetch).get()


def _feishu_send(config: Any, token_mgr: Any, chat_id: str, text: str) -> None:
    import requests

    token = _feishu_token(config, token_mgr)
    requests.post(
        "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "receive_id": chat_id,
            "msg_type": "text",
            "content": json.dumps({"text": text[:2000]}, ensure_ascii=False),
        },
        timeout=15,
    ).raise_for_status()


def _feishu_reply_rich(config: Any, token_mgr: Any, chat_id: str, text: str) -> None:
    """Reply with a markdown card (converted for Feishu's subset); fall back
    to plain text when the card cannot be sent."""
    if _feishu_send_card(config, token_mgr, chat_id, text) is None:
        _feishu_send(config, token_mgr, chat_id, text)


_FEISHU_MD_HEADER_RE = re.compile(r"^ {0,3}(#{1,6})\s+(.*?)\s*#*\s*$", re.MULTILINE)
_FEISHU_MD_HR_RE = re.compile(r"^ {0,3}(?:-{3,}|\*{3,}|_{3,})\s*$", re.MULTILINE)
_FEISHU_MD_TABLE_DELIM_RE = re.compile(r"^\s*\|?\s*:?-{2,}[\s:|-]*\|?\s*$")
_FEISHU_MD_HTML_LINK_RE = re.compile(r'<a\s+href="([^"]+)"[^>]*>(.*?)</a>', re.S)


def _feishu_split_table_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _feishu_convert_tables(text: str) -> str:
    """GFM tables → bold header line plus one bullet per row of
    ``**column**: value`` pairs (Feishu card markdown has no tables)."""
    lines = text.split("\n")
    out: list[str] = []
    i = 0
    while i < len(lines):
        is_table_start = (
            lines[i].lstrip().startswith("|")
            and i + 1 < len(lines)
            and _FEISHU_MD_TABLE_DELIM_RE.match(lines[i + 1]) is not None
            and "-" in lines[i + 1]
        )
        if not is_table_start:
            out.append(lines[i])
            i += 1
            continue
        header = _feishu_split_table_row(lines[i])
        i += 2
        while i < len(lines) and lines[i].lstrip().startswith("|"):
            cells = _feishu_split_table_row(lines[i])
            if any(cells):
                pairs = " · ".join(
                    f"**{h}**: {c}" if h else c
                    for h, c in zip(header, cells, strict=False)
                )
                out.append(f"- {pairs}")
            i += 1
        out.append("")
    return "\n".join(out)


def _feishu_markdown(text: str) -> str:
    """Translate chat markdown/HTML into the subset Feishu card markdown
    renders: headings become bold lines, HTML conveniences become markdown,
    tables become bullet rows. Code fences, lists, quotes, bold/italic and
    links pass through untouched."""
    # HTML conveniences the chat engine sometimes emits
    text = (
        text.replace("<br>", "\n")
        .replace("<br/>", "\n")
        .replace("<br />", "\n")
        .replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
    )
    text = _FEISHU_MD_HTML_LINK_RE.sub(r"[\2](\1)", text)
    text = re.sub(r"</?(?:b|strong)>", "**", text)
    text = re.sub(r"</?(?:i|em)>", "*", text)
    text = re.sub(r"</?code>", "`", text)
    # Remaining angle brackets are content (e.g. <任务内容>), not tags —
    # full-width them instead of stripping, the markdown element would eat them
    text = text.replace("<", "＜").replace(">", "＞")
    # headings → bold lines
    text = _FEISHU_MD_HEADER_RE.sub(lambda m: f"**{m.group(2)}**", text)
    # horizontal rules → a plain dash line
    text = _FEISHU_MD_HR_RE.sub("———", text)
    return _feishu_convert_tables(text)


def _feishu_card_content(text: str) -> str:
    """Interactive-card payload rendering ``text`` with the card markdown
    module (wider syntax support than lark_md inside a div)."""
    return json.dumps(
        {
            "config": {"update_multi": True},
            "elements": [{"tag": "markdown", "content": _feishu_markdown(text)}],
        },
        ensure_ascii=False,
    )


def _feishu_send_card(
    config: Any, token_mgr: Any, chat_id: str, text: str
) -> str | None:
    """Send an interactive card and return its message id (None on failure,
    letting the caller fall back to a plain text reply)."""
    import requests

    try:
        token = _feishu_token(config, token_mgr)
        resp = requests.post(
            "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "receive_id": chat_id,
                "msg_type": "interactive",
                "content": _feishu_card_content(text),
            },
            timeout=15,
        )
        resp.raise_for_status()
        return str(resp.json().get("data", {}).get("message_id")) or None
    except Exception:
        logger.warning("feishu card send failed; falling back to text", exc_info=True)
        return None


def _feishu_update_card(
    config: Any, token_mgr: Any, message_id: str, text: str
) -> None:
    """PATCH the card body in place; failures are logged, never raised —
    a missed intermediate update must not kill the answer."""
    import requests

    try:
        token = _feishu_token(config, token_mgr)
        requests.patch(
            f"https://open.feishu.cn/open-apis/im/v1/messages/{message_id}",
            headers={"Authorization": f"Bearer {token}"},
            json={"content": _feishu_card_content(text)},
            timeout=15,
        ).raise_for_status()
    except Exception:
        logger.warning("feishu card update failed for %s", message_id, exc_info=True)


def dispatch_im_notification(
    *, user_id: Any, title: str, description: str | None, link: str | None = None
) -> bool:
    """Best-effort DM push for approval cards / loop-held outputs.

    Looks up the user's newest IM binding and DMs through that
    platform's provider config. Returns True when delivered.
    """
    try:
        from onyx.db.engine.sql_engine import get_session_with_current_tenant
        from onyx.db.enums import SSOProviderType
        from onyx.db.sso_provider import fetch_sso_providers

        with get_session_with_current_tenant() as db_session:
            binding = binding_for_user(db_session, user_id)
            if binding is None:
                return False
            platform_type = {
                "wecom": SSOProviderType.WECOM,
                "dingtalk": SSOProviderType.DINGTALK,
                "feishu": SSOProviderType.FEISHU,
            }[binding.platform]
            config = None
            for provider in fetch_sso_providers(db_session, enabled_only=True):
                if provider.provider_type is platform_type:
                    from onyx.server.china_sso import _config_for

                    config = _config_for(provider, dict(provider.config or {}))
                    break
            if config is None:
                return False
        text = title if not description else f"{title}\n{description}"
        if link:
            text = f"{text}\n{link}"
        message = InboundMessage(
            platform=binding.platform,
            msg_id=f"push-{uuid4().hex[:8]}",
            platform_user_id=binding.platform_user_id,
            chat_id=binding.chat_id,
            text="",
        )
        _send_reply(message, config, text)
        return True
    except Exception:
        logger.exception("IM notification dispatch failed")
        return False
