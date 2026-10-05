"""Platform adapters: parse callbacks, echo verifications, normalize events.

Each adapter is pure parsing over already-verified/decrypted payloads
plus the config accessor; sending lives in ``framework._send_reply``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from onyx.onyxbot.china import crypto
from onyx.onyxbot.china.framework import (
    CallbackRejected,
    InboundAttachment,
    InboundMessage,
)


@dataclass(frozen=True)
class CallbackResult:
    """What the router should answer inline (fast path)."""

    status: int = 200
    body: dict[str, Any] | None = None
    message: InboundMessage | None = None  # non-None → answer async


# ── WeCom ─────────────────────────────────────────────────────────────────

WECOM_XML_TEXT_FIELD = "<Content><![CDATA["


def wecom_handle(
    config: Any, query: dict[str, str], body: dict[str, Any], headers: dict[str, str]
) -> CallbackResult:
    del headers
    """WeCom callback: GET query carries msg_signature/timestamp/nonce,
    body carries Encrypt; the decrypted payload is XML."""
    signature = query.get("msg_signature", "")
    timestamp = query.get("timestamp", "")
    nonce = query.get("nonce", "")
    encrypted = str(body.get("Encrypt") or body.get("encrypt") or "")
    if not encrypted:
        raise CallbackRejected("wecom callback without Encrypt")
    if config.bot_token is None or config.bot_encoding_aes_key is None:
        raise CallbackRejected("wecom bot not configured on this provider")
    try:
        plaintext = crypto.wecom_verify_echo(
            token=config.bot_token,
            encoding_aes_key=config.bot_encoding_aes_key,
            signature=signature,
            timestamp=timestamp,
            nonce=nonce,
            encrypted_b64=encrypted,
            corp_id=config.corp_id,
        )
    except crypto.CallbackCryptoError as exc:
        raise CallbackRejected(str(exc)) from exc

    msg_type, fields = _wecom_parse_xml(plaintext)
    if msg_type == "echo":
        return CallbackResult(body={"msg": fields["echo"]})
    if msg_type != "text":
        return CallbackResult()  # non-text events acknowledged, not answered
    return CallbackResult(
        message=InboundMessage(
            platform="wecom",
            msg_id=fields["msg_id"],
            platform_user_id=fields["from"],
            chat_id=fields["from"],
            text=fields["content"],
        )
    )


def _wecom_parse_xml(xml: str) -> tuple[str, dict[str, str]]:
    """Minimal field extraction for WeCom's flat callback XML."""
    import re

    def field(name: str) -> str:
        m = re.search(
            rf"<{name}><!\[CDATA\[(.*?)\]\]></{name}>|<{name}>(.*?)</{name}>",
            xml,
            re.S,
        )
        if not m:
            return ""
        return m.group(1) if m.group(1) is not None else m.group(2)

    msg_type = field("MsgType")
    if not msg_type:
        # URL verification decrypts to the bare echo string
        return "echo", {"echo": xml.strip()}
    return msg_type, {
        "msg_id": field("MsgId") or field("CreateTime"),
        "from": field("FromUserName"),
        "content": field("Content").strip(),
    }


# ── DingTalk ──────────────────────────────────────────────────────────────


def dingtalk_handle(
    config: Any, query: dict[str, str], body: dict[str, Any], headers: dict[str, str]
) -> CallbackResult:
    del query
    """DingTalk enterprise robot: body {encrypt}; URL verification carries
    the literal 'success' plaintext, normal events carry a JSON payload."""
    del headers
    encrypted = str(body.get("encrypt") or "")
    if not encrypted:
        raise CallbackRejected("dingtalk callback without encrypt")
    if config.bot_aes_key is None:
        raise CallbackRejected("dingtalk bot not configured on this provider")
    try:
        plaintext = crypto.dingtalk_decrypt(config.bot_aes_key, encrypted)
    except crypto.CallbackCryptoError as exc:
        raise CallbackRejected(str(exc)) from exc

    if plaintext.strip().strip('"') == "success":
        return CallbackResult(
            body={"encrypt": crypto.dingtalk_encrypt(config.bot_aes_key, "success")}
        )

    try:
        payload = json.loads(plaintext)
    except json.JSONDecodeError:
        return CallbackResult()
    return _dingtalk_parse_payload(payload)


def _dingtalk_parse_payload(payload: dict[str, Any]) -> CallbackResult:
    # conversation + sender may be nested (1.0) or flat (stream-less robots)
    conversation = payload.get("conversationId") or ""
    sender = payload.get("senderStaffId") or payload.get("senderId") or ""
    text = (
        payload.get("text", {}).get("content", "")
        if isinstance(payload.get("text"), dict)
        else str(payload.get("text") or "")
    )
    msg_id = str(payload.get("msgId") or payload.get("messageId") or "")
    if not (sender and text):
        return CallbackResult()
    return CallbackResult(
        message=InboundMessage(
            platform="dingtalk",
            msg_id=msg_id,
            platform_user_id=sender,
            chat_id=conversation or sender,
            text=text.strip(),
            sender_name=str(payload.get("senderNick") or ""),
        )
    )


# ── Feishu ────────────────────────────────────────────────────────────────


def _parse_feishu_message_content(
    msg_type: str, content: dict[str, Any], message_id: str
) -> tuple[str, list[InboundAttachment]] | None:
    """Extract (text, attachments) from one im message body; ``None`` for
    message types the bot does not answer (audio/media/stickers/shares)."""
    text = ""
    attachments: list[InboundAttachment] = []
    if msg_type == "text":
        text = str(content.get("text", ""))
    elif msg_type == "image":
        image_key = str(content.get("image_key") or "")
        if image_key:
            attachments.append(InboundAttachment("image", image_key, "", message_id))
    elif msg_type == "file":
        file_key = str(content.get("file_key") or "")
        file_name = str(content.get("file_name") or "file")
        if file_key:
            attachments.append(
                InboundAttachment("file", file_key, file_name, message_id)
            )
    elif msg_type == "post":
        # rich text: paragraphs carry text/img fragments
        texts: list[str] = []
        post = content.get("content")
        if isinstance(post, dict):
            for paragraphs in post.values():
                if not isinstance(paragraphs, list):
                    continue
                for paragraph in paragraphs:
                    if not isinstance(paragraph, list):
                        continue
                    for node in paragraph:
                        if not isinstance(node, dict):
                            continue
                        if node.get("tag") == "text":
                            texts.append(str(node.get("text") or ""))
                        elif node.get("tag") == "img":
                            image_key = str(node.get("image_key") or "")
                            if image_key:
                                attachments.append(
                                    InboundAttachment(
                                        "image", image_key, "", message_id
                                    )
                                )
        text = "\n".join(part for part in texts if part).strip()
    else:
        return None
    if msg_type == "text" and not text:
        return None
    if msg_type in ("image", "file") and not attachments:
        return None
    return text, attachments


def feishu_handle(
    config: Any, query: dict[str, str], body: dict[str, Any], headers: dict[str, str]
) -> CallbackResult:
    del query, headers
    """Feishu event subscription: optional encrypt envelope; url
    verification echoes the challenge; im.message.receive_v1 carries text."""
    if config.bot_verification_token is None:
        raise CallbackRejected("feishu bot not configured on this provider")
    try:
        payload = crypto.parse_feishu_body(body, config.bot_encrypt_key)
    except crypto.CallbackCryptoError as exc:
        raise CallbackRejected(str(exc)) from exc

    if payload.get("type") == "url_verification":
        try:
            crypto.feishu_verify_token(
                config.bot_verification_token, payload.get("token")
            )
        except crypto.CallbackCryptoError as exc:
            raise CallbackRejected(str(exc)) from exc
        return CallbackResult(body={"challenge": payload.get("challenge", "")})

    # v2 event schema: header + event
    header = payload.get("header") or {}
    try:
        crypto.feishu_verify_token(config.bot_verification_token, header.get("token"))
    except crypto.CallbackCryptoError as exc:
        raise CallbackRejected(str(exc)) from exc
    event_type = str(header.get("event_type") or "")
    if event_type != "im.message.receive_v1":
        return CallbackResult()
    event = payload.get("event") or {}
    message = event.get("message") or {}
    msg_type = str(message.get("message_type") or "")
    sender_id = ((event.get("sender") or {}).get("sender_id") or {}).get(
        "open_id"
    ) or ""
    chat_id = str(message.get("chat_id") or sender_id)
    msg_id = str(message.get("message_id") or "")
    if not sender_id:
        return CallbackResult()

    try:
        content = json.loads(message.get("content") or "{}")
    except json.JSONDecodeError:
        content = {}

    parsed = _parse_feishu_message_content(msg_type, content, msg_id)
    if parsed is None:
        return CallbackResult()
    text, attachments = parsed
    return CallbackResult(
        message=InboundMessage(
            platform="feishu",
            msg_id=msg_id,
            platform_user_id=sender_id,
            chat_id=chat_id,
            text=text,
            attachments=tuple(attachments),
        )
    )


HANDLERS = {
    "wecom": wecom_handle,
    "dingtalk": dingtalk_handle,
    "feishu": feishu_handle,
}
