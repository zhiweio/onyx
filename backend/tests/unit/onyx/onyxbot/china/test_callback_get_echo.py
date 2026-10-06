"""GET callback handshake tests (WeCom URL verification; DingTalk 200 probe; 405 for Feishu)."""

import base64
import struct
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any
from unittest.mock import patch

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from fastapi import FastAPI
from fastapi.testclient import TestClient

from onyx.server.onyxbot_china_api import router


@contextmanager
def _null_session():
    yield None


def _pad(data: bytes) -> bytes:
    pad = 32 - len(data) % 32
    return data + bytes([pad]) * pad


KEY_32 = bytes(range(32))
WECOM_AES_KEY = base64.b64encode(KEY_32).decode().rstrip("=")
CORP_ID = "ww-corp-1"


@dataclass
class _WeComConfig:
    corp_id: str = CORP_ID
    bot_token: str = "tok"
    bot_encoding_aes_key: str = WECOM_AES_KEY


def _encrypt(plaintext: str) -> str:
    msg = plaintext.encode()
    envelope = b"R" * 16 + struct.pack(">I", len(msg)) + msg + CORP_ID.encode()
    enc = Cipher(algorithms.AES(KEY_32), modes.CBC(KEY_32[:16])).encryptor()
    return base64.b64encode(enc.update(_pad(envelope)) + enc.finalize()).decode()


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_wecom_get_echo_returns_plaintext() -> None:
    from onyx.onyxbot.china import crypto

    echo = "verify-me-1234"
    encrypted = _encrypt(echo)
    signature = crypto.wecom_signature("tok", "1700000000", "n1", encrypted)

    with (
        patch(
            "onyx.server.onyxbot_china_api.get_session_with_current_tenant",
            _null_session,
        ),
        patch(
            "onyx.server.onyxbot_china_api._bot_configs",
            return_value=[_WeComConfig()],
        ),
    ):
        resp = _client().get(
            "/onyxbot/wecom/callback",
            params={
                "msg_signature": signature,
                "timestamp": "1700000000",
                "nonce": "n1",
                "echostr": encrypted,
            },
        )
    assert resp.status_code == 200
    assert resp.text == echo


def test_wecom_get_echo_rejects_bad_signature() -> None:
    encrypted = _encrypt("verify-me")
    with (
        patch(
            "onyx.server.onyxbot_china_api.get_session_with_current_tenant",
            _null_session,
        ),
        patch(
            "onyx.server.onyxbot_china_api._bot_configs",
            return_value=[_WeComConfig()],
        ),
    ):
        resp = _client().get(
            "/onyxbot/wecom/callback",
            params={
                "msg_signature": "bad",
                "timestamp": "1700000000",
                "nonce": "n1",
                "echostr": encrypted,
            },
        )
    assert resp.status_code == 403


def test_dingtalk_get_probe_answers_200() -> None:
    """DingTalk's console probes the callback with a bare GET that must
    answer 200 before the platform accepts the URL."""
    resp = _client().get("/onyxbot/dingtalk/callback")
    assert resp.status_code == 200
    assert resp.text == "success"


def test_feishu_get_answers_405() -> None:
    with patch("onyx.server.onyxbot_china_api._bot_configs", return_value=[]):
        resp = _client().get("/onyxbot/feishu/callback")
        assert resp.status_code == 405


DING_AES_KEY = base64.b64encode(bytes(range(64, 96))).decode()
DING_APP_KEY = "dk"


@dataclass
class _DingConfig:
    client_id: str = DING_APP_KEY
    client_secret: str = "ds"
    email_domain: str = "corp.example.cn"
    robot_code: str = "rc1"
    bot_aes_key: str = DING_AES_KEY
    bot_token: str | None = None
    bot_card_template_id: str | None = None


def _dingtalk_encrypt(plaintext: str) -> str:
    """DingTalk envelope: same layout as WeCom but the suffix is the AppKey
    and the key comes straight from the 44-char base64 aes_key."""
    key = base64.b64decode(DING_AES_KEY)
    msg = plaintext.encode()
    envelope = b"R" * 16 + struct.pack(">I", len(msg)) + msg + DING_APP_KEY.encode()
    enc = Cipher(algorithms.AES(key), modes.CBC(key[:16])).encryptor()
    return base64.b64encode(enc.update(_pad(envelope)) + enc.finalize()).decode()


def test_wecom_post_callback_dispatches_answer() -> None:
    """A valid encrypted POST text message runs the full chain: verify →
    decrypt → parse → dedup check → background answer dispatch."""
    from onyx.onyxbot.china import crypto

    xml = (
        "<xml><ToUserName><![CDATA[ww1]]></ToUserName>"
        "<MsgType><![CDATA[text]]></MsgType>"
        "<Content><![CDATA[你好Onyx]]></Content>"
        "<FromUserName><![CDATA[zhang]]></FromUserName>"
        "<MsgId>123</MsgId></xml>"
    )
    encrypted = _encrypt(xml)
    signature = crypto.wecom_signature("tok", "1700000000", "n1", encrypted)
    dispatched: list[Any] = []
    with (
        patch(
            "onyx.server.onyxbot_china_api.get_session_with_current_tenant",
            _null_session,
        ),
        patch(
            "onyx.server.onyxbot_china_api._bot_configs",
            return_value=[_WeComConfig()],
        ),
        patch(
            "onyx.server.onyxbot_china_api.seen_before",
            return_value=False,
        ),
        patch(
            "onyx.server.onyxbot_china_api.answer_message_async",
            side_effect=lambda message, _config: dispatched.append(message),
        ),
    ):
        resp = _client().post(
            "/onyxbot/wecom/callback",
            params={
                "msg_signature": signature,
                "timestamp": "1700000000",
                "nonce": "n1",
            },
            json={"Encrypt": encrypted},
        )
    assert resp.status_code == 200
    assert resp.json() == {"code": 0}
    assert len(dispatched) == 1
    message = dispatched[0]
    assert message.text == "你好Onyx"
    assert message.platform_user_id == "zhang"
    assert message.msg_id == "123"


def test_wecom_post_callback_dedup_skips_answer() -> None:
    from onyx.onyxbot.china import crypto

    xml = (
        "<xml><ToUserName><![CDATA[ww1]]></ToUserName>"
        "<MsgType><![CDATA[text]]></MsgType>"
        "<Content><![CDATA[retry]]></Content>"
        "<FromUserName><![CDATA[zhang]]></FromUserName>"
        "<MsgId>123</MsgId></xml>"
    )
    encrypted = _encrypt(xml)
    signature = crypto.wecom_signature("tok", "1700000000", "n1", encrypted)
    dispatched: list[Any] = []
    with (
        patch(
            "onyx.server.onyxbot_china_api.get_session_with_current_tenant",
            _null_session,
        ),
        patch(
            "onyx.server.onyxbot_china_api._bot_configs",
            return_value=[_WeComConfig()],
        ),
        patch("onyx.server.onyxbot_china_api.seen_before", return_value=True),
        patch(
            "onyx.server.onyxbot_china_api.answer_message_async",
            side_effect=lambda message, _config: dispatched.append(message),
        ),
    ):
        resp = _client().post(
            "/onyxbot/wecom/callback",
            params={
                "msg_signature": signature,
                "timestamp": "1700000000",
                "nonce": "n1",
            },
            json={"Encrypt": encrypted},
        )
    assert resp.status_code == 200
    assert dispatched == []


def test_dingtalk_post_callback_dispatches_answer() -> None:
    import json

    payload = json.dumps(
        {
            "msgId": "m1",
            "senderStaffId": "staff-9",
            "conversationId": "cidD",
            "conversationType": "1",
            "text": {"content": "hi"},
        }
    )
    encrypted = _dingtalk_encrypt(payload)
    dispatched: list[Any] = []
    with (
        patch(
            "onyx.server.onyxbot_china_api.get_session_with_current_tenant",
            _null_session,
        ),
        patch(
            "onyx.server.onyxbot_china_api._bot_configs",
            return_value=[_DingConfig()],
        ),
        patch("onyx.server.onyxbot_china_api.seen_before", return_value=False),
        patch(
            "onyx.server.onyxbot_china_api.answer_message_async",
            side_effect=lambda message, _config: dispatched.append(message),
        ),
    ):
        resp = _client().post("/onyxbot/dingtalk/callback", json={"encrypt": encrypted})
    assert resp.status_code == 200
    assert resp.json() == {"code": 0}
    assert len(dispatched) == 1
    message = dispatched[0]
    assert message.text == "hi"
    assert message.platform_user_id == "staff-9"
    assert message.is_group is False


def test_dingtalk_post_check_url_echoes_without_answer() -> None:
    """The console's encrypted channel check gets the signed success echo and
    never reaches the answer flow."""
    from onyx.onyxbot.china import crypto

    encrypted = _dingtalk_encrypt('{"EventType":"check_url"}')
    # bot_token set → the incoming request must carry its own valid signature
    timestamp, nonce = "1700000000", "n1"
    signature = crypto.dingtalk_signature("tok", timestamp, nonce, encrypted)
    dispatched: list[Any] = []
    config = _DingConfig(bot_token="tok")  # hardened echo carries msg_signature
    with (
        patch(
            "onyx.server.onyxbot_china_api.get_session_with_current_tenant",
            _null_session,
        ),
        patch(
            "onyx.server.onyxbot_china_api._bot_configs",
            return_value=[config],
        ),
        patch(
            "onyx.server.onyxbot_china_api.answer_message_async",
            side_effect=lambda message, _config: dispatched.append(message),
        ),
    ):
        resp = _client().post(
            "/onyxbot/dingtalk/callback",
            params={"signature": signature, "timestamp": timestamp, "nonce": nonce},
            json={"encrypt": encrypted},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("encrypt")
    assert {"msg_signature", "timeStamp", "nonce"} <= set(body)
    assert body["msg_signature"] == crypto.dingtalk_signature(
        "tok", body["timeStamp"], body["nonce"], body["encrypt"]
    )
    assert dispatched == []
