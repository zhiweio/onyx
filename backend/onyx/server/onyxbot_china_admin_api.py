"""Admin endpoints for the China IM bots.

Read-only status plus a credential verify action. Bot configuration lives on
the SSO provider rows (see docs/mainland/im-bot-deployment.md); this surface
never duplicates that store.
"""

from __future__ import annotations

from typing import Any

import requests
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from onyx.auth.permissions import require_permission
from onyx.db.engine.sql_engine import get_session
from onyx.db.enums import Permission, SSOProviderType
from onyx.db.models import ChinaIMBinding, User
from onyx.db.sso_provider import fetch_sso_providers
from onyx.server.china_sso import _config_for
from onyx.utils.logger import setup_logger

logger = setup_logger()

admin_router = APIRouter(prefix="/admin/onyxbot-china")

_BOT_PLATFORMS: dict[str, SSOProviderType] = {
    "wecom": SSOProviderType.WECOM,
    "dingtalk": SSOProviderType.DINGTALK,
    "feishu": SSOProviderType.FEISHU,
}

_VERIFY_TIMEOUT_SECONDS = 15


def _identifier_for(platform: str, config: Any) -> str | None:
    if platform == "wecom":
        return config.corp_id
    if platform == "dingtalk":
        return config.client_id
    return config.app_id


def _bot_fields_set(platform: str, config: Any) -> bool:
    if platform == "wecom":
        return bool(config.bot_token and config.bot_encoding_aes_key)
    if platform == "dingtalk":
        return bool(config.robot_code and config.bot_aes_key)
    return bool(config.bot_verification_token and config.bot_encrypt_key)


def _mask(value: str) -> str:
    if len(value) <= 4:
        return "*" * len(value)
    return value[:4] + "*" * min(len(value) - 4, 8)


def _fetch_token(platform: str, config: Any) -> str:
    """Fetch an app/tenant token to prove the credentials work."""
    if platform == "wecom":
        resp = requests.get(
            "https://qyapi.weixin.qq.com/cgi-bin/gettoken",
            params={"corpid": config.corp_id, "corpsecret": config.corp_secret},
            timeout=_VERIFY_TIMEOUT_SECONDS,
        )
        data = resp.json()
        if "access_token" not in data:
            raise RuntimeError(str(data.get("errmsg", "token fetch failed")))
        return str(data["access_token"])

    if platform == "dingtalk":
        resp = requests.post(
            "https://api.dingtalk.com/v1.0/oauth2/accessToken",
            json={"appKey": config.client_id, "appSecret": config.client_secret},
            timeout=_VERIFY_TIMEOUT_SECONDS,
        )
        data = resp.json()
        if "accessToken" not in data:
            raise RuntimeError(str(data.get("message", "token fetch failed")))
        return str(data["accessToken"])

    resp = requests.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": config.app_id, "app_secret": config.app_secret},
        timeout=_VERIFY_TIMEOUT_SECONDS,
    )
    data = resp.json()
    if data.get("code") != 0 or "tenant_access_token" not in data:
        raise RuntimeError(str(data.get("msg", "token fetch failed")))
    return str(data["tenant_access_token"])


class ChinaBotPlatformStatus(BaseModel):
    platform: str
    provider_count: int
    bot_ready: bool
    app_id: str | None
    bound_users: int


class ChinaBotsStatusResponse(BaseModel):
    platforms: list[ChinaBotPlatformStatus]


class ChinaBotVerifyResponse(BaseModel):
    ok: bool
    detail: str | None = None


def _platform_status(
    platform: str, provider_type: SSOProviderType, db_session: Session
) -> ChinaBotPlatformStatus:
    configs = [
        _config_for(provider, dict(provider.config or {}))
        for provider in fetch_sso_providers(db_session, enabled_only=True)
        if provider.provider_type is provider_type
    ]
    ready_configs = [c for c in configs if _bot_fields_set(platform, c)]
    identifier = next(
        (_identifier_for(platform, c) for c in ready_configs + configs if c), None
    )
    bound_users = (
        db_session.query(func.count(ChinaIMBinding.id))
        .filter(ChinaIMBinding.platform == platform)
        .scalar()
        or 0
    )
    return ChinaBotPlatformStatus(
        platform=platform,
        provider_count=len(configs),
        bot_ready=bool(ready_configs),
        app_id=_mask(identifier) if identifier else None,
        bound_users=bound_users,
    )


@admin_router.get("/status")
def china_bots_status(
    current_user: User = Depends(
        require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)
    ),
    db_session: Session = Depends(get_session),
) -> ChinaBotsStatusResponse:
    del current_user
    return ChinaBotsStatusResponse(
        platforms=[
            _platform_status(platform, provider_type, db_session)
            for platform, provider_type in _BOT_PLATFORMS.items()
        ]
    )


@admin_router.post("/{platform}/verify")
def verify_china_bot(
    platform: str,
    current_user: User = Depends(
        require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)
    ),
    db_session: Session = Depends(get_session),
) -> ChinaBotVerifyResponse:
    del current_user
    provider_type = _BOT_PLATFORMS.get(platform)
    if provider_type is None:
        return ChinaBotVerifyResponse(ok=False, detail="unknown platform")

    configs = [
        _config_for(provider, dict(provider.config or {}))
        for provider in fetch_sso_providers(db_session, enabled_only=True)
        if provider.provider_type is provider_type
    ]
    ready_configs = [c for c in configs if _bot_fields_set(platform, c)]
    if not ready_configs:
        return ChinaBotVerifyResponse(ok=False, detail="bot credentials missing")

    try:
        _fetch_token(platform, ready_configs[0])
    except Exception as exc:
        logger.warning("china bot verify failed (%s): %s", platform, exc)
        return ChinaBotVerifyResponse(ok=False, detail=str(exc))
    return ChinaBotVerifyResponse(ok=True)
