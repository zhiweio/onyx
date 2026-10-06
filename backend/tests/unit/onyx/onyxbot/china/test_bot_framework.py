"""Unit tests for the China IM bot framework: crypto, adapters, dedup."""

import base64
import hashlib
import json
import struct
from collections.abc import Callable

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
    bot_token: str | None = None
    bot_card_template_id: str | None = None


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


def test_feishu_card_content_shape() -> None:
    import json as _json

    from onyx.onyxbot.china.framework import _feishu_card_content

    card = _json.loads(_feishu_card_content("你好 **世界**"))
    assert card["config"] == {"update_multi": True}
    assert card["elements"][0]["tag"] == "markdown"
    assert card["elements"][0]["content"] == "你好 **世界**"


def test_reset_command_set_covers_aliases() -> None:
    from onyx.onyxbot.china.framework import _RESET_COMMANDS

    for cmd in ("/reset", "/新对话", "新对话"):
        assert cmd in _RESET_COMMANDS
    # plain chat must never trip the reset path
    assert "今天天气怎么样" not in _RESET_COMMANDS


def test_feishu_markdown_converts_headings_and_rules() -> None:
    from onyx.onyxbot.china.framework import _feishu_markdown

    md = _feishu_markdown("## 概览\n内容\n\n---\n后续")
    assert "**概览**" in md
    assert "## " not in md
    assert "———" in md


def test_feishu_markdown_converts_tables() -> None:
    from onyx.onyxbot.china.framework import _feishu_markdown

    table = "| 项目 | 数值 |\n|---|---|\n| 人口 | 82.9万 |\n| GDP | 3150亿 |\n"
    md = _feishu_markdown(table)
    assert "| 项目 | 数值 |" not in md
    # header row becomes the bullet's bold keys; data rows follow
    assert "- **项目**: 人口 · **数值**: 82.9万" in md
    assert "- **项目**: GDP · **数值**: 3150亿" in md


def test_feishu_markdown_converts_html() -> None:
    from onyx.onyxbot.china.framework import _feishu_markdown

    md = _feishu_markdown(
        '行1<br>行2 <a href="https://x.cn">链接</a> <b>加粗</b> &amp; 更多'
        " /场景 <名称> <任务内容>"
    )
    assert "<br>" not in md and "<a " not in md and "<b>" not in md
    assert "[链接](https://x.cn)" in md
    assert "**加粗**" in md
    assert "&" in md and "&amp;" not in md
    # content angle brackets survive as full-width, not stripped as tags
    assert "＜名称＞ ＜任务内容＞" in md


def test_feishu_card_content_uses_markdown_module() -> None:
    import json as _json

    from onyx.onyxbot.china.framework import _feishu_card_content

    card = _json.loads(_feishu_card_content("# 标题"))
    assert card["elements"][0]["tag"] == "markdown"
    assert card["elements"][0]["content"] == "**标题**"


def test_help_and_scenario_list_commands_registered() -> None:
    from onyx.onyxbot.china.framework import (
        _HELP_COMMANDS,
        _SCENARIO_LIST_COMMANDS,
        _help_reply,
    )

    assert "/帮助" in _HELP_COMMANDS and "/help" in _HELP_COMMANDS
    # Feishu custom-menu items send their label as the message, so the menu
    # labels must be registered aliases
    assert "使用帮助" in _HELP_COMMANDS
    assert "/场景列表" in _SCENARIO_LIST_COMMANDS
    assert "我的场景" in _SCENARIO_LIST_COMMANDS
    reply = _help_reply()
    assert "/场景" in reply and "/reset" in reply and "/场景列表" in reply


def test_feishu_reply_rich_falls_back_to_text(monkeypatch) -> None:
    from onyx.onyxbot.china import framework

    sent = {}
    monkeypatch.setattr(
        framework,
        "_feishu_send_card",
        lambda _config, _mgr, _chat_id, _text: None,
    )
    monkeypatch.setattr(
        framework,
        "_feishu_send",
        lambda _config, _mgr, chat_id, text: sent.update(chat_id=chat_id, text=text),
    )
    framework._feishu_reply_rich("cfg", "mgr", "oc_1", "**hi**")
    assert sent == {"chat_id": "oc_1", "text": "**hi**"}


def test_feishu_reply_rich_uses_card(monkeypatch) -> None:
    from onyx.onyxbot.china import framework

    text_sent = {}
    fallback_used = []
    monkeypatch.setattr(
        framework,
        "_feishu_send_card",
        lambda _config, _mgr, _chat_id, text: text_sent.update(text=text) or "om_1",
    )
    monkeypatch.setattr(
        framework,
        "_feishu_send",
        lambda _config, _mgr, _chat_id, text: fallback_used.append(text),
    )
    framework._feishu_reply_rich("cfg", "mgr", "oc_1", "**hi**")
    assert text_sent["text"] == "**hi**"
    assert fallback_used == []


def test_split_for_cards_prefers_paragraph_boundaries() -> None:
    from onyx.onyxbot.china.framework import _split_for_cards

    text = "段落一\n\n" + "x" * 200 + "\n\n" + "段落二\n\n" + "y" * 200
    chunks = _split_for_cards(text, 150)
    assert len(chunks) >= 2
    for chunk in chunks:
        assert len(chunk) <= 150 or "\n\n" not in chunk[:150]
    assert "".join(c.replace("\n", "") for c in chunks).startswith("段落一")


def test_split_for_cards_hard_cuts_oversized_paragraph() -> None:
    from onyx.onyxbot.china.framework import _split_for_cards

    chunks = _split_for_cards("z" * 500, 120)
    assert all(len(c) <= 120 for c in chunks)
    assert "".join(chunks) == "z" * 500


def test_split_for_cards_single_chunk_short_text() -> None:
    from onyx.onyxbot.china.framework import _split_for_cards

    assert _split_for_cards("短文本", 100) == ["短文本"]


# ── dingtalk: signature, group parse, card streaming ──────────────────────


def test_dingtalk_signature_verification_optional() -> None:
    key = base64.b64decode(DING_AES_KEY)
    payload = {
        "conversationId": "cid01",
        "senderStaffId": "staff-9",
        "conversationType": "1",
        "text": {"content": "hi"},
        "msgId": "m1",
    }
    encrypted = base64.b64encode(
        _aes_encrypt(key, _envelope(json.dumps(payload), ""))
    ).decode()

    cfg = _DingCfg()
    cfg.bot_token = "tok"
    timestamp, nonce = "1700000000", "n1"
    signature = crypto.dingtalk_signature("tok", timestamp, nonce, encrypted)
    ok = adapters.dingtalk_handle(
        cfg,
        {"signature": signature, "timestamp": timestamp, "nonce": nonce},
        {"encrypt": encrypted},
        {},
    )
    assert ok.message is not None

    # bad / missing signature params are refused
    with pytest.raises(CallbackRejected):
        adapters.dingtalk_handle(
            cfg,
            {"signature": "bad", "timestamp": timestamp, "nonce": nonce},
            {"encrypt": encrypted},
            {},
        )
    with pytest.raises(CallbackRejected):
        adapters.dingtalk_handle(cfg, {}, {"encrypt": encrypted}, {})

    # no token configured → signature unchecked
    result = adapters.dingtalk_handle(_DingCfg(), {}, {"encrypt": encrypted}, {})
    assert result.message is not None


def test_dingtalk_parse_sets_group_flag() -> None:
    parse = adapters._dingtalk_parse_payload
    group = parse(
        {
            "conversationId": "cidG",
            "senderStaffId": "s1",
            "conversationType": "2",
            "text": {"content": "hello"},
        }
    )
    assert group.message is not None and group.message.is_group is True
    direct = parse(
        {
            "conversationId": "cidD",
            "senderStaffId": "s1",
            "conversationType": "1",
            "text": {"content": "hello"},
        }
    )
    assert direct.message is not None and direct.message.is_group is False


def test_dingtalk_card_start_targets_conversation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from onyx.onyxbot.china import framework

    calls: list[tuple[str, str, dict]] = []
    monkeypatch.setattr(
        framework,
        "_dingtalk_card_api",
        lambda _config, _mgr, method, path, payload: calls.append(
            (method, path, payload)
        ),
    )
    monkeypatch.setattr(framework.time, "sleep", lambda _s: None)

    cfg = _DingCfg()
    cfg.bot_card_template_id = "tpl1"
    message = framework.InboundMessage(
        platform="dingtalk",
        msg_id="m1",
        platform_user_id="staff-9",
        chat_id="cidG",
        text="hi",
        is_group=True,
    )
    out_track_id = framework._dingtalk_card_start(message, cfg, None)
    assert out_track_id is not None
    method, path, create_payload = calls[0]
    assert (method, path) == ("POST", "/v1.0/card/instances")
    assert create_payload["cardTemplateId"] == "tpl1"
    assert create_payload["callbackType"] == "STREAM"
    _, _, deliver = calls[1]
    assert deliver["openSpaceId"] == "dtv1.card//IM_GROUP.cidG"
    assert deliver["imGroupOpenDeliverModel"] == {"robotCode": "rc1"}

    # no template configured → no card
    assert framework._dingtalk_card_start(message, _DingCfg(), None) is None


def test_dingtalk_card_finish_frames(monkeypatch: pytest.MonkeyPatch) -> None:
    from onyx.onyxbot.china import framework

    calls: list[tuple[str, str, dict]] = []
    monkeypatch.setattr(
        framework,
        "_dingtalk_card_api",
        lambda _config, _mgr, method, path, payload: calls.append(
            (method, path, payload)
        ),
    )
    monkeypatch.setattr(framework.time, "sleep", lambda _s: None)

    framework._dingtalk_card_finish("cfg", None, "track-1", "最终回答")
    method, path, stream_payload = calls[0]
    assert (method, path) == ("PUT", "/v1.0/card/streaming")
    assert stream_payload["outTrackId"] == "track-1"
    assert stream_payload["key"] == "msgContent"
    assert stream_payload["content"].startswith("最终回答")
    assert framework._DINGTALK_COMMAND_HINT in stream_payload["content"]
    assert stream_payload["isFull"] is True
    assert stream_payload["isFinalize"] is True
    _, _, flow_payload = calls[1]
    params = flow_payload["cardData"]["cardParamMap"]
    assert params["flowStatus"] == framework._DINGTALK_FLOW_FINISHED
    assert params["msgContent"].startswith("最终回答")


def test_dingtalk_send_group_vs_direct(monkeypatch: pytest.MonkeyPatch) -> None:
    from onyx.onyxbot.china import framework

    posts: list[tuple[str, dict]] = []
    monkeypatch.setattr(framework, "_dingtalk_token", lambda _config, _mgr: "tok")
    monkeypatch.setattr(
        "requests.post",
        lambda url, **kwargs: (
            posts.append((url, kwargs.get("json") or {}))
            or type("R", (), {"raise_for_status": lambda _self: None})()
        ),
    )

    cfg = _DingCfg()
    framework._dingtalk_send(cfg, None, "cidG", "staff-9", "群里回答", is_group=True)
    url, body = posts[0]
    assert url.endswith("/v1.0/robot/groupMessages/send")
    assert body["openConversationId"] == "cidG"
    assert body["robotCode"] == "rc1"
    assert json.loads(body["msgParam"])["text"].startswith("群里回答")

    framework._dingtalk_send(cfg, None, "cidD", "staff-9", "单聊回答")
    url, body = posts[1]
    assert url.endswith("/v1.0/robot/oToMessages/batchSend")
    assert body["userIds"] == ["staff-9"]
    assert json.loads(body["msgParam"])["content"].startswith("单聊回答")


def test_dingtalk_reply_rich_falls_back_without_template(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from onyx.onyxbot.china import framework

    sends: list[tuple[str, bool]] = []
    monkeypatch.setattr(
        framework,
        "_dingtalk_send",
        lambda _config, _mgr, _chat_id, _user_id, text, *, is_group=False: sends.append(
            (text, is_group)
        ),
    )
    message = framework.InboundMessage(
        platform="dingtalk",
        msg_id="m1",
        platform_user_id="staff-9",
        chat_id="cidD",
        text="hi",
    )
    framework._dingtalk_reply_rich(message, _DingCfg(), None, "命令回复")
    assert sends == [("命令回复", False)]


def test_dingtalk_check_url_echo_carries_appkey_suffix() -> None:
    """The console decrypts our echo reply and validates the envelope suffix
    against the app's AppKey (suiteKey), per the official crypto SDK."""
    from onyx.onyxbot.china import adapters

    result = adapters._dingtalk_echo_response(_DingCfg(), "success")
    assert result.body is not None
    encrypt = result.body["encrypt"]
    # Console-side decrypt: key + padding, then suffix must equal the AppKey.
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    key = base64.b64decode(DING_AES_KEY + "=" * (-len(DING_AES_KEY) % 4))
    dec = Cipher(algorithms.AES(key), modes.CBC(key[:16])).decryptor()
    raw = dec.update(base64.b64decode(encrypt)) + dec.finalize()
    raw = raw[: -raw[-1]]  # strip PKCS7 padding
    msg_len = struct.unpack(">I", raw[16:20])[0]
    suffix = raw[20 + msg_len :].decode()
    assert suffix == "dk"
    assert raw[20 : 20 + msg_len].decode() == "success"


def test_dingtalk_answer_streams_card_frames(monkeypatch: pytest.MonkeyPatch) -> None:
    """The streaming answer writes throttled INPUTING frames into the card and
    closes with one finalize frame plus the FINISHED flow state."""
    from onyx.onyxbot.china import framework
    from onyx.server.query_and_chat.placement import Placement
    from onyx.server.query_and_chat.streaming_models import (
        AgentResponseDelta,
        Packet,
    )

    calls: list[tuple[str, str, dict]] = []
    monkeypatch.setattr(
        framework,
        "_dingtalk_card_api",
        lambda _config, _mgr, method, path, payload: calls.append(
            (method, path, payload)
        ),
    )
    monkeypatch.setattr(framework.time, "sleep", lambda _s: None)
    # monotonic call order: init, delta1 check, post-update stamp, delta2 check
    clock = iter([0.0, 10.0, 10.0, 10.6])
    monkeypatch.setattr(framework.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(framework, "_prepare_turn", lambda _msg, _cfg: object())
    monkeypatch.setattr(
        framework,
        "_iter_chat_stream",
        lambda _prepared: iter(
            [
                Packet(
                    placement=Placement(turn_index=0),
                    obj=AgentResponseDelta(content="第一段"),
                ),
                Packet(
                    placement=Placement(turn_index=0),
                    obj=AgentResponseDelta(content="第二段"),
                ),
            ]
        ),
    )
    monkeypatch.setattr(
        framework, "_dingtalk_card_start", lambda _msg, _cfg, _mgr: "track-1"
    )

    message = framework.InboundMessage(
        platform="dingtalk",
        msg_id="m1",
        platform_user_id="staff-9",
        chat_id="cidD",
        text="hi",
    )
    framework._answer_dingtalk(message, _DingCfg())

    methods = [(m, p) for m, p, _ in calls]
    assert methods == [
        ("PUT", "/v1.0/card/instances"),  # throttled INPUTING update
        ("PUT", "/v1.0/card/streaming"),  # finalize frame
        ("PUT", "/v1.0/card/instances"),  # FINISHED flow state
    ]
    params = calls[0][2]["cardData"]["cardParamMap"]
    assert params["flowStatus"] == framework._DINGTALK_FLOW_INPUTING
    # only the first delta had accumulated when the throttle window opened
    assert params["msgContent"].startswith("第一段")
    stream_payload = calls[1][2]
    assert stream_payload["isFinalize"] is True
    assert stream_payload["content"].startswith("第一段第二段")
    assert calls[2][2]["cardData"]["cardParamMap"]["flowStatus"] == (
        framework._DINGTALK_FLOW_FINISHED
    )


def test_dingtalk_answer_marks_card_failed_on_stream_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from onyx.chat.models import StreamingError
    from onyx.onyxbot.china import framework
    from onyx.server.query_and_chat.placement import Placement
    from onyx.server.query_and_chat.streaming_models import (
        AgentResponseDelta,
        Packet,
    )

    calls: list[tuple[str, str, dict]] = []
    monkeypatch.setattr(
        framework,
        "_dingtalk_card_api",
        lambda _config, _mgr, method, path, payload: calls.append(
            (method, path, payload)
        ),
    )
    monkeypatch.setattr(framework.time, "sleep", lambda _s: None)
    clock = iter([0.0, 10.0])
    monkeypatch.setattr(framework.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(framework, "_prepare_turn", lambda _msg, _cfg: object())
    monkeypatch.setattr(
        framework,
        "_iter_chat_stream",
        lambda _prepared: iter(
            [
                StreamingError(error="boom"),
                Packet(
                    placement=Placement(turn_index=0),
                    obj=AgentResponseDelta(content="x"),
                ),
            ]
        ),
    )
    monkeypatch.setattr(
        framework, "_dingtalk_card_start", lambda _msg, _cfg, _mgr: "track-1"
    )

    message = framework.InboundMessage(
        platform="dingtalk",
        msg_id="m1",
        platform_user_id="staff-9",
        chat_id="cidD",
        text="hi",
    )
    framework._answer_dingtalk(message, _DingCfg())

    assert len(calls) == 1
    params = calls[0][2]["cardData"]["cardParamMap"]
    assert params["flowStatus"] == framework._DINGTALK_FLOW_FAILED
    assert "boom" in params["msgContent"]


def test_wecom_send_posts_text_message(monkeypatch: pytest.MonkeyPatch) -> None:
    from onyx.onyxbot.china import framework

    gets: list[tuple[str, dict]] = []
    posts: list[tuple[str, dict]] = []

    def fake_get(
        url: str, params: dict[str, str] | None = None, **_kwargs: object
    ) -> object:
        gets.append((url, params or {}))
        return type(
            "R", (), {"json": lambda _self: {"access_token": "tok", "expires_in": 7200}}
        )()

    def fake_post(
        url: str, json: dict[str, object] | None = None, **_kwargs: object
    ) -> object:
        posts.append((url, json or {}))
        return type("R", (), {"raise_for_status": lambda _self: None})()

    monkeypatch.setattr("requests.get", fake_get)
    monkeypatch.setattr("requests.post", fake_post)

    class _TokenMgr:
        def __init__(self, fetch: Callable[[], tuple[str, int]]) -> None:
            self._fetch = fetch

        def get(self) -> str:
            token, _expires = self._fetch()
            return token

    framework._wecom_send(_WeComCfg(), _TokenMgr, "zhang", "回答")

    url, params = gets[0]
    assert url == "https://qyapi.weixin.qq.com/cgi-bin/gettoken"
    assert params["corpid"] == "ww1" and params["corpsecret"] == "s"

    url, body = posts[0]
    assert url == "https://qyapi.weixin.qq.com/cgi-bin/message/send"
    assert body["touser"] == "zhang"
    assert body["msgtype"] == "text"
    assert body["agentid"] == 1000002
    assert body["text"]["content"] == "回答"


def test_wecom_send_truncates_to_message_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from onyx.onyxbot.china import framework

    bodies: list[dict] = []
    monkeypatch.setattr(
        "requests.get",
        lambda _url, **_kw: type(
            "R", (), {"json": lambda _self: {"access_token": "tok"}}
        )(),
    )
    monkeypatch.setattr(
        "requests.post",
        lambda _url, **kwargs: (
            bodies.append(kwargs.get("json") or {})
            or type("R", (), {"raise_for_status": lambda _self: None})()
        ),
    )

    class _TokenMgr:
        def __init__(self, fetch: Callable[[], tuple[str, int]]) -> None:
            self._fetch = fetch

        def get(self) -> str:
            token, _expires = self._fetch()
            return token

    framework._wecom_send(_WeComCfg(), _TokenMgr, "zhang", "x" * 2500)
    assert len(bodies[0]["text"]["content"]) == 2000


def test_seen_before_dedups_by_msg_id(monkeypatch: pytest.MonkeyPatch) -> None:
    from onyx.onyxbot.china import framework

    class _FakeRedis:
        def __init__(self) -> None:
            self.keys: set[str] = set()

        def set(self, key: str, _value: str, ex: int, nx: bool) -> bool:
            del ex
            assert nx is True
            if key in self.keys:
                return False
            self.keys.add(key)
            return True

    fake = _FakeRedis()
    monkeypatch.setattr(
        # called as get_redis_client(tenant_id=...); swallow the kwarg
        "onyx.redis.redis_pool.get_redis_client",
        lambda **_kwargs: fake,
    )
    monkeypatch.setattr(
        "shared_configs.contextvars.get_current_tenant_id", lambda: "tenant"
    )

    assert framework.seen_before("dingtalk", "m1") is False
    # platform retries of the same msg id are dropped
    assert framework.seen_before("dingtalk", "m1") is True
    assert framework.seen_before("dingtalk", "m2") is False
    assert framework.seen_before("wecom", "m1") is False

    # redis down → fail closed (drop the callback rather than double-answer)
    def _broken(_tenant_id: str) -> object:
        raise RuntimeError("redis down")

    monkeypatch.setattr("onyx.redis.redis_pool.get_redis_client", _broken)
    assert framework.seen_before("dingtalk", "m3") is True


def test_wecom_click_menu_event_maps_to_command() -> None:
    """A WeCom chat-menu click (MsgType=event, Event=click) is answered as if
    the user had sent the button's EventKey command text."""
    from onyx.onyxbot.china import adapters

    xml = (
        "<xml><ToUserName><![CDATA[ww1]]></ToUserName>"
        "<MsgType><![CDATA[event]]></MsgType>"
        "<Event><![CDATA[click]]></Event>"
        "<EventKey><![CDATA[使用帮助]]></EventKey>"
        "<FromUserName><![CDATA[zhang]]></FromUserName>"
        "<CreateTime>1750000000</CreateTime></xml>"
    )
    encrypted = base64.b64encode(
        _aes_encrypt(AES_KEY_32, _envelope(xml, "ww1"))
    ).decode()
    token, timestamp, nonce = "tok", "1700000000", "n1"
    signature = crypto.wecom_signature(token, timestamp, nonce, encrypted)

    result = adapters.wecom_handle(
        _WeComCfg(),
        {"msg_signature": signature, "timestamp": timestamp, "nonce": nonce},
        {"Encrypt": encrypted},
        {},
    )
    assert result.message is not None
    assert result.message.text == "使用帮助"
    assert result.message.platform_user_id == "zhang"
    # menu events carry no MsgId; the dedup id composes time+user+key
    assert result.message.msg_id == "1750000000-zhang-使用帮助"


def test_wecom_non_click_event_is_acknowledged() -> None:
    from onyx.onyxbot.china import adapters

    xml = (
        "<xml><ToUserName><![CDATA[ww1]]></ToUserName>"
        "<MsgType><![CDATA[event]]></MsgType>"
        "<Event><![CDATA[subscribe]]></Event>"
        "<FromUserName><![CDATA[zhang]]></FromUserName>"
        "<CreateTime>1750000000</CreateTime></xml>"
    )
    encrypted = base64.b64encode(
        _aes_encrypt(AES_KEY_32, _envelope(xml, "ww1"))
    ).decode()
    signature = crypto.wecom_signature("tok", "1700000000", "n1", encrypted)
    result = adapters.wecom_handle(
        _WeComCfg(),
        {"msg_signature": signature, "timestamp": "1700000000", "nonce": "n1"},
        {"Encrypt": encrypted},
        {},
    )
    assert result.message is None


def test_wecom_menu_create_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    from onyx.onyxbot.china import framework

    posts: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        "requests.get",
        lambda _url, **_kw: type(
            "R", (), {"json": lambda _self: {"access_token": "tok"}}
        )(),
    )

    def fake_post(url: str, json: dict | None = None, **_kw: object) -> object:
        posts.append((url, json or {}))
        return type(
            "R",
            (),
            {
                "json": lambda _self: {"errcode": 0},
                "raise_for_status": lambda _self: None,
            },
        )()

    monkeypatch.setattr("requests.post", fake_post)

    class _TokenMgr:
        def __init__(self, fetch: Callable[[], tuple[str, int]]) -> None:
            self._fetch = fetch

        def get(self) -> str:
            token, _expires = self._fetch()
            return token

    body = framework._wecom_menu_create(_WeComCfg(), _TokenMgr)
    assert body == {"errcode": 0}
    url, payload = posts[0]
    assert url.startswith("https://qyapi.weixin.qq.com/cgi-bin/menu/create")
    buttons = payload["button"]
    # two submenus + one top-level click button, every leaf maps to an alias
    assert len(buttons) == 3
    leaves = [b for b in buttons if "key" in b]
    subs = [s for b in buttons for s in b.get("sub_button", [])]
    assert {leaf["key"] for leaf in leaves} == {"使用帮助"}
    assert {s["key"] for s in subs} == {"新对话", "我的任务", "我的场景", "技能"}
    assert all(s["type"] == "click" for s in subs)


def test_dingtalk_reply_appends_command_hint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from onyx.onyxbot.china import framework

    bodies: list[dict] = []
    monkeypatch.setattr(framework, "_dingtalk_token", lambda _config, _mgr: "tok")

    def fake_post(_url: str, json: dict | None = None, **_kw: object) -> object:
        bodies.append(json or {})
        return type("R", (), {"raise_for_status": lambda _self: None})()

    monkeypatch.setattr("requests.post", fake_post)

    framework._dingtalk_send(_DingCfg(), None, "cidD", "staff-9", "回答正文")
    content = json.loads(bodies[0]["msgParam"])["content"]
    assert content.startswith("回答正文")
    assert framework._DINGTALK_COMMAND_HINT in content


def test_skill_command_not_feishu_gated() -> None:
    """The skill command (menu label 技能) must answer on every platform."""
    import inspect

    from onyx.onyxbot.china import framework

    src = inspect.getsource(framework._prepare_turn)
    skill_branch = src[src.index('command == "技能"') :]
    header = skill_branch[: skill_branch.index("return")]
    assert "feishu" not in header
