"""GET callback handshake tests (WeCom URL verification; 405 for others)."""

import base64
import struct
from contextlib import contextmanager
from dataclasses import dataclass
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


def test_non_wecom_get_answers_405() -> None:
    with patch("onyx.server.onyxbot_china_api._bot_configs", return_value=[]):
        for platform in ("dingtalk", "feishu"):
            resp = _client().get(f"/onyxbot/{platform}/callback")
            assert resp.status_code == 405
