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

import json
import re
import threading
import time
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

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

# Feishu interactive-card streaming: throttle cadence and size limits.
# lark_md in cards renders most markdown but not tables; very long answers
# overflow the card, so they fall back to a plain text message.
_FEISHU_CARD_UPDATE_INTERVAL_SECONDS = 1.5
_FEISHU_CARD_MAX_CHARS = 3500


class CallbackRejected(Exception):
    """Verification refused the callback; router answers 403."""


@dataclass(frozen=True)
class InboundMessage:
    platform: str  # wecom | dingtalk | feishu
    msg_id: str
    platform_user_id: str
    chat_id: str  # group or DM conversation id
    text: str
    sender_name: str = ""


@dataclass(frozen=True)
class _PreparedTurn:
    """Everything the chat engine needs after binding/scenario handling."""

    email: str
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
        user = get_user_by_email(email, db_session)
        if user is None:
            user = _provision_bot_user(db_session, email)
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

        start_fresh = _consume_reset_flag(message.platform, message.platform_user_id)
        session_id = None if start_fresh else _latest_session_id(db_session, user.id)

        trigger_reply = try_scenario_trigger(db_session, user, message.text)
        if trigger_reply is not None:
            return trigger_reply

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
    )
    return _PreparedTurn(email=email, request=request)


def _iter_chat_stream(prepared: _PreparedTurn) -> Any:
    """Open the chat-engine stream for one turn; hold the DB session open
    for as long as the caller consumes the generator."""
    from onyx.chat.process_message import handle_stream_message_objects
    from onyx.db.engine.sql_engine import get_session_with_current_tenant
    from onyx.db.users import get_user_by_email

    with get_session_with_current_tenant() as db_session:
        fresh_user = get_user_by_email(prepared.email, db_session)
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
        _feishu_send(provider_config, token_mgr, message.chat_id, prepared)
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
    if len(display) <= _FEISHU_CARD_MAX_CHARS:
        _feishu_update_card(provider_config, token_mgr, card_msg_id, display)
        return

    # Too long for one card: truncate the card preview and DM the full text.
    _feishu_update_card(
        provider_config,
        token_mgr,
        card_msg_id,
        display[:_FEISHU_CARD_MAX_CHARS] + "\n\n……(内容较长,完整回答已单独发送)",
    )
    _feishu_send(provider_config, token_mgr, message.chat_id, display)


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


def _help_reply() -> str:
    return (
        "🤖 **Onyx 机器人使用指南**\n"
        "- 直接发消息即可提问:回答会检索已接入的知识库(如飞书知识库)并按需联网\n"
        "- **/场景** <名称> <任务内容>:启动自动化场景任务\n"
        "- **/场景列表**:查看当前可用的场景\n"
        "- **/reset**:开启新对话(清除上下文;长期记忆保留)\n"
        "- **/帮助**:显示本指南"
    )


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
            config, AppTokenManager, message.chat_id, message.platform_user_id, text
        )
    elif message.platform == "feishu":
        _feishu_send(config, AppTokenManager, message.chat_id, text)
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


def _dingtalk_send(
    config: Any, token_mgr: Any, _chat_id: str, user_id: str, text: str
) -> None:
    import requests

    def fetch() -> tuple[str, int]:
        resp = requests.post(
            "https://api.dingtalk.com/v1.0/oauth2/accessToken",
            json={"appKey": config.client_id, "appSecret": config.client_secret},
            timeout=15,
        )
        data = resp.json()
        return str(data["accessToken"]), int(data.get("expireIn", 7200))

    token = token_mgr(fetch).get()
    requests.post(
        "https://api.dingtalk.com/v1.0/robot/oToMessages/batchSend",
        headers={"x-acs-dingtalk-access-token": token},
        json={
            "robotCode": config.robot_code,
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
    text = re.sub(r"<[^>]+>", "", text)
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
