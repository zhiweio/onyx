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
import threading
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from onyx.utils.logger import setup_logger

logger = setup_logger()

# Bound concurrent background answers per api_server process; the
# platform retries callbacks, so overflow is dropped with a log.
_MAX_CONCURRENT_ANSWERS = 8
_answer_semaphore = threading.Semaphore(_MAX_CONCURRENT_ANSWERS)

BOT_EMAIL_DOMAIN_FALLBACK = "im.local"


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
        reply = _answer(message, provider_config)
        if reply:
            _send_reply(message, provider_config, reply)
    except Exception:
        logger.exception("china bot answer failed for %s", message.msg_id)
    finally:
        _answer_semaphore.release()


def _answer(message: InboundMessage, provider_config: Any) -> str | None:
    """Provision the user and run one in-process chat turn.

    ``/场景`` commands bypass the chat turn and start a CraftJob instead."""
    from onyx.chat.process_message import (
        gather_stream,
        handle_stream_message_objects,
    )
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
        chat_session_info=ChatSessionCreationRequest(),
    )
    from onyx.db.engine.sql_engine import get_session_with_current_tenant as _sess

    with _sess() as db_session:
        from onyx.db.users import get_user_by_email as _by_email

        fresh_user = _by_email(email, db_session)
        assert fresh_user is not None
        answer_stream = handle_stream_message_objects(
            request, fresh_user, bypass_acl=False
        )
        response = gather_stream(answer_stream)
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


def _feishu_send(config: Any, token_mgr: Any, chat_id: str, text: str) -> None:
    import requests

    def fetch() -> tuple[str, int]:
        resp = requests.post(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": config.app_id, "app_secret": config.app_secret},
            timeout=15,
        )
        data = resp.json()
        return str(data["tenant_access_token"]), int(data.get("expire", 7200))

    token = token_mgr(fetch).get()
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
