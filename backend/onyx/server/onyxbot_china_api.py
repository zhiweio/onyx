"""HTTP callback endpoints for the China IM bots.

Mounted under ``/onyxbot`` (no ``/api`` prefix: platforms are pointed at
these URLs directly and some strip prefixes; nginx routes them). No
session auth — the per-platform signature verification *is* the
authentication. Answering happens on a background thread; the endpoint
itself always replies within the platforms' 1-5s window.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from onyx.db.engine.sql_engine import get_session_with_current_tenant
from onyx.db.enums import SSOProviderType
from onyx.db.sso_provider import fetch_sso_providers
from onyx.onyxbot.china import adapters
from onyx.onyxbot.china.framework import (
    CallbackRejected,
    answer_message_async,
    seen_before,
)
from onyx.server.china_sso import _config_for
from onyx.utils.logger import setup_logger

logger = setup_logger()

router = APIRouter(prefix="/onyxbot")

_PLATFORM_TYPES = {
    "wecom": SSOProviderType.WECOM,
    "dingtalk": SSOProviderType.DINGTALK,
    "feishu": SSOProviderType.FEISHU,
}


def _bot_configs(db_session: Any, platform: str) -> list[Any]:
    provider_type = _PLATFORM_TYPES.get(platform)
    if provider_type is None:
        return []
    return [
        _config_for(provider, dict(provider.config or {}))
        for provider in fetch_sso_providers(db_session, enabled_only=True)
        if provider.provider_type is provider_type
    ]


@router.post("/{platform}/callback")
async def china_bot_callback(platform: str, request: Request) -> JSONResponse:
    if platform not in _PLATFORM_TYPES:
        return JSONResponse({"error": "unknown platform"}, status_code=404)
    try:
        body = await request.json()
        if not isinstance(body, dict):
            raise CallbackRejected("body must be an object")
    except Exception:
        return JSONResponse({"error": "bad body"}, status_code=400)

    query = {k: v for k, v in request.query_params.items()}
    headers = {k: v for k, v in request.headers.items()}

    handler = adapters.HANDLERS[platform]
    with get_session_with_current_tenant() as db_session:
        configs = _bot_configs(db_session, platform)
    if not configs:
        return JSONResponse({"error": "bot not configured"}, status_code=404)

    last_error: Exception | None = None
    for config in configs:
        try:
            result = handler(config, query, body, headers)
        except CallbackRejected as exc:
            last_error = exc
            continue
        except Exception:
            logger.exception("china bot handler crash (%s)", platform)
            return JSONResponse({"error": "handler error"}, status_code=500)
        break
    else:
        logger.warning("china bot %s callback rejected: %s", platform, last_error)
        return JSONResponse({"error": "verification failed"}, status_code=403)

    if result.message is not None:
        if seen_before(platform, result.message.msg_id):
            return JSONResponse({"code": 0})
        answer_message_async(result.message, config)
    return JSONResponse(result.body if result.body is not None else {"code": 0})
