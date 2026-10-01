"""Unit tests for the China IM bot framework: crypto, adapters, dedup."""

import base64
import hashlib
import json
import struct

import pytest
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from onyx.onyxbot.china import adapters, crypto
from onyx.onyxbot.china.framework import (
    CallbackRejected,
    deterministic_email,
)

# ── envelope helpers (mirror the platform construction) ───────────────────


def _pad(data: bytes) -> bytes:
    pad = 32 - len(data) % 32
    return data + bytes([pad]) * pad


def _aes_encrypt(key: bytes, plaintext: bytes) -> bytes:
    enc = Cipher(algorithms.AES(key), modes.CBC(key[:16])).encryptor()
    return enc.update(_pad(plaintext)) + enc.finalize()


def _envelope(msg: str, suffix: str, random_block: bytes = b"R" * 16) -> bytes:
    msg_bytes = msg.encode("utf-8")
    return (
        random_block + struct.pack(">I", len(msg_bytes)) + msg_bytes + suffix.encode()
    )


# 43-char EncodingAESKey (base64 of a 32-byte key without padding)
AES_KEY_32 = bytes(range(32))
WECOM_AES_KEY = base64.b64encode(AES_KEY_32).decode().rstrip("=")
assert len(WECOM_AES_KEY) == 43

DING_AES_KEY = base64.b64encode(bytes(range(64, 96))).decode()  # normal b64


def test_wecom_roundtrip_and_signature() -> None:
    xml = (
        "<xml><ToUserName><![CDATA[ww1]]></ToUserName>"
        "<MsgType><![CDATA[text]]></MsgType>"
        "<Content><![CDATA[你好Onyx]]></Content>"
        "<FromUserName><![CDATA[zhang]]></FromUserName>"
        "<MsgId>123</MsgId></xml>"
    )
    encrypted = base64.b64encode(
        _aes_encrypt(AES_KEY_32, _envelope(xml, "ww1"))
    ).decode()
    token, timestamp, nonce = "tok", "1700000000", "n1"
    signature = crypto.wecom_signature(token, timestamp, nonce, encrypted)

    msg, corp = crypto.wecom_decrypt(WECOM_AES_KEY, encrypted)
    assert msg == xml
    assert corp == "ww1"

    echo = crypto.wecom_verify_echo(
        token=WECOM_AES_KEY and "tok",
        encoding_aes_key=WECOM_AES_KEY,
        signature=signature,
        timestamp=timestamp,
        nonce=nonce,
        encrypted_b64=encrypted,
        corp_id="ww1",
    )
    assert echo == xml

    with pytest.raises(crypto.CallbackCryptoError, match="signature"):
        crypto.wecom_verify_echo(
            token="tok",
            encoding_aes_key=WECOM_AES_KEY,
            signature="bad",
            timestamp=timestamp,
            nonce=nonce,
            encrypted_b64=encrypted,
            corp_id="ww1",
        )
    with pytest.raises(crypto.CallbackCryptoError, match="corp"):
        crypto.wecom_verify_echo(
            token="tok",
            encoding_aes_key=WECOM_AES_KEY,
            signature=signature,
            timestamp=timestamp,
            nonce=nonce,
            encrypted_b64=encrypted,
            corp_id="other",
        )


def test_dingtalk_echo_roundtrip() -> None:
    key = base64.b64decode(DING_AES_KEY)
    encrypted = base64.b64encode(_aes_encrypt(key, _envelope("success", ""))).decode()
    echo = crypto.dingtalk_verify_echo(DING_AES_KEY, encrypted)
    # the echoed cipher decrypts back to success
    assert crypto.dingtalk_decrypt(DING_AES_KEY, echo) == "success"

    bad = base64.b64encode(_aes_encrypt(key, _envelope("hello", ""))).decode()
    with pytest.raises(crypto.CallbackCryptoError, match="verification payload"):
        crypto.dingtalk_verify_echo(DING_AES_KEY, bad)


def test_feishu_decrypt_and_parse() -> None:
    key = hashlib.sha256(b"fs-encrypt").digest()
    payload = {"type": "url_verification", "challenge": "abc123", "token": "t1"}
    encrypted = base64.b64encode(
        _aes_encrypt(key, _envelope(json.dumps(payload), ""))
    ).decode()

    parsed = crypto.parse_feishu_body({"encrypt": encrypted}, "fs-encrypt")
    assert parsed["challenge"] == "abc123"

    with pytest.raises(crypto.CallbackCryptoError, match="no key"):
        crypto.parse_feishu_body({"encrypt": encrypted}, None)


# ── adapters ──────────────────────────────────────────────────────────────


class _WeComCfg:
    corp_id = "ww1"
    corp_secret = "s"
    agent_id = "1000002"
    email_domain = "corp.example.cn"
    bot_token: str | None = "tok"
    bot_encoding_aes_key = WECOM_AES_KEY


class _DingCfg:
    client_id = "dk"
    client_secret = "ds"
    email_domain = "corp.example.cn"
    robot_code = "rc1"
    bot_aes_key = DING_AES_KEY


class _FeishuCfg:
    app_id = "cli_a"
    app_secret = "fs"
    email_domain = "corp.example.cn"
    bot_verification_token = "t1"
    bot_encrypt_key = "fs-encrypt"


def test_wecom_adapter_text_message() -> None:
    xml = (
        "<xml><MsgType><![CDATA[text]]></MsgType>"
        "<Content><![CDATA[ 帮我查报销制度 ]]></Content>"
        "<FromUserName><![CDATA[zhang]]></FromUserName>"
        "<MsgId>777</MsgId></xml>"
    )
    encrypted = base64.b64encode(
        _aes_encrypt(AES_KEY_32, _envelope(xml, "ww1"))
    ).decode()
    query = {
        "msg_signature": crypto.wecom_signature("tok", "1", "n", encrypted),
        "timestamp": "1",
        "nonce": "n",
    }
    result = adapters.wecom_handle(_WeComCfg(), query, {"Encrypt": encrypted}, {})
    assert result.message is not None
    assert result.message.platform == "wecom"
    assert result.message.platform_user_id == "zhang"
    assert result.message.text == "帮我查报销制度"


def test_wecom_adapter_rejects_when_unconfigured() -> None:
    cfg = _WeComCfg()
    cfg.bot_token = None
    with pytest.raises(CallbackRejected, match="not configured"):
        adapters.wecom_handle(cfg, {}, {"Encrypt": "x"}, {})


def test_dingtalk_adapter_message_and_echo() -> None:
    key = base64.b64decode(DING_AES_KEY)
    payload = {
        "conversationId": "cid01",
        "senderStaffId": "staff-9",
        "senderNick": "李四",
        "msgId": "m1",
        "text": {"content": " What is the leave policy "},
    }
    encrypted = base64.b64encode(
        _aes_encrypt(key, _envelope(json.dumps(payload), ""))
    ).decode()

    result = adapters.dingtalk_handle(_DingCfg(), {}, {"encrypt": encrypted}, {})
    assert result.message is not None
    assert result.message.platform_user_id == "staff-9"
    assert result.message.chat_id == "cid01"
    assert result.message.text == "What is the leave policy"
    assert result.message.sender_name == "李四"

    echo_enc = base64.b64encode(_aes_encrypt(key, _envelope("success", ""))).decode()
    echo = adapters.dingtalk_handle(_DingCfg(), {}, {"encrypt": echo_enc}, {})
    assert echo.body is not None and "encrypt" in echo.body


def test_feishu_adapter_url_verification_and_message() -> None:
    cfg = _FeishuCfg()
    # url verification (unencrypted body)
    result = adapters.feishu_handle(
        cfg, {}, {"type": "url_verification", "challenge": "ch1", "token": "t1"}, {}
    )
    assert result.body == {"challenge": "ch1"}
    # wrong token
    with pytest.raises(CallbackRejected):
        adapters.feishu_handle(
            cfg, {}, {"type": "url_verification", "challenge": "x", "token": "bad"}, {}
        )

    # encrypted im.message.receive_v1
    key = hashlib.sha256(b"fs-encrypt").digest()
    event = {
        "header": {"event_type": "im.message.receive_v1", "token": "t1"},
        "event": {
            "sender": {"sender_id": {"open_id": "ou_9"}},
            "message": {
                "message_id": "om_1",
                "chat_id": "oc_1",
                "message_type": "text",
                "content": json.dumps(
                    {"text": "Q3 financial risk control"}, ensure_ascii=False
                ),
            },
        },
    }
    encrypted = base64.b64encode(
        _aes_encrypt(key, _envelope(json.dumps(event), ""))
    ).decode()
    result = adapters.feishu_handle(cfg, {}, {"encrypt": encrypted}, {})
    assert result.message is not None
    assert result.message.platform_user_id == "ou_9"
    assert result.message.text == "Q3 financial risk control"

    # non-text messages acknowledged silently
    event_nt = {
        "header": {"event_type": "im.message.receive_v1", "token": "t1"},
        "event": {
            "sender": {"sender_id": {"open_id": "ou_9"}},
            "message": {
                "message_id": "om_2",
                "chat_id": "oc_1",
                "message_type": "image",
                "content": "{}",
            },
        },
    }
    result = adapters.feishu_handle(cfg, {}, event_nt, {})
    assert result.message is None


def test_deterministic_email() -> None:
    assert (
        deterministic_email("wecom", "zhang", _WeComCfg())
        == "wecom-zhang@corp.example.cn"
    )
    assert (
        deterministic_email("feishu", "ou_1", type("C", (), {"email_domain": None})())
        == "feishu-ou_1@im.local"
    )
