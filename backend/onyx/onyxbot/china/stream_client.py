"""DingTalk Stream-mode bot client.

A long-lived outbound WebSocket connection (official ``dingtalk-stream``
SDK) that receives robot messages without any public callback URL — the
reachability problems of tunneled HTTP callbacks don't apply. Messages
arrive as the same JSON shape the HTTP callback decrypts to, so parsing,
dedup, and answering reuse the HTTP path untouched.

One client thread per enabled DINGTALK SSO provider with bot credentials;
started from the api_server lifespan. Config changes need a restart.
"""

import threading

from onyx.utils.logger import setup_logger

logger = setup_logger()

_LOCK = threading.Lock()
_THREADS: dict[int, threading.Thread] = {}


def _handler_for(config: object) -> "dingtalk_stream.CallbackHandler":  # noqa: F821
    import dingtalk_stream

    from onyx.onyxbot.china.adapters import parse_robot_payload
    from onyx.onyxbot.china.framework import answer_message_async, seen_before

    class _StreamChatbotHandler(dingtalk_stream.ChatbotHandler):
        async def process(self, callback: "dingtalk_stream.CallbackMessage"):  # noqa: F821
            try:
                payload = callback.data
                if not isinstance(payload, dict):
                    return dingtalk_stream.AckMessage.STATUS_OK, "OK"
                result = parse_robot_payload(payload)
                if result.message is None:
                    return dingtalk_stream.AckMessage.STATUS_OK, "OK"
                if seen_before("dingtalk", result.message.msg_id):
                    return dingtalk_stream.AckMessage.STATUS_OK, "OK"
                answer_message_async(result.message, config)
            except Exception:
                logger.exception("dingtalk stream message handling failed")
            return dingtalk_stream.AckMessage.STATUS_OK, "OK"

    return _StreamChatbotHandler()


def start_stream_client(provider_id: int, config: object) -> bool:
    """Start (or keep) the stream client for one provider. Returns whether a
    new thread was started."""
    import dingtalk_stream

    with _LOCK:
        existing = _THREADS.get(provider_id)
        if existing is not None and existing.is_alive():
            return False
        credential = dingtalk_stream.Credential(config.client_id, config.client_secret)
        client = dingtalk_stream.DingTalkStreamClient(credential)
        client.register_callback_handler(
            dingtalk_stream.ChatbotMessage.TOPIC, _handler_for(config)
        )
        thread = threading.Thread(
            target=client.start_forever,
            name=f"dingtalk-stream-{provider_id}",
            daemon=True,
        )
        thread.start()
        _THREADS[provider_id] = thread
        logger.info("dingtalk stream client started provider_id=%s", provider_id)
        return True


def start_enabled_stream_clients() -> list[int]:
    """Start a stream client for every enabled DINGTALK provider with bot
    credentials. Best-effort: a DB or SDK failure logs and returns []."""
    try:
        from onyx.db.engine.sql_engine import get_session_with_current_tenant
        from onyx.db.enums import SSOProviderType
        from onyx.db.sso_provider import fetch_sso_providers
        from onyx.server.china_sso import _config_for

        started: list[int] = []
        with get_session_with_current_tenant() as db_session:
            for provider in fetch_sso_providers(db_session, enabled_only=True):
                if provider.provider_type is not SSOProviderType.DINGTALK:
                    continue
                stored = (
                    provider.config.get_value(apply_mask=False)
                    if provider.config
                    else {}
                )
                config = _config_for(provider, dict(stored))
                # Same enablement marker as the HTTP callback bot.
                if getattr(config, "bot_aes_key", None) is None:
                    continue
                if start_stream_client(provider.id, config):
                    started.append(provider.id)
        return started
    except Exception:
        logger.exception("failed to start dingtalk stream clients")
        return []
