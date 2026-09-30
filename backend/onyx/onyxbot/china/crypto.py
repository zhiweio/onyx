"""Callback cryptography for the China IM platforms (pure functions).

All three platforms wrap callback payloads in the same AES-256-CBC
envelope family — random(16) + msg_len(4, big endian) + msg (+ suffix) —
with per-platform key derivation and signature schemes:

- WeCom: key = Base64Decode(EncodingAESKey + "="), signature =
  SHA-1 over the sorted (token, timestamp, nonce, encrypt) tuple; the
  envelope suffix is the corp_id.
- DingTalk (enterprise robot): key = Base64Decode(aesKey), no signature
  header; URL verification decrypts to a JSON payload whose content is
  echoed back re-encrypted.
- Feishu: key = SHA-256(encrypt_key); no signature (the token field in
  the body is checked); URL verification echoes ``challenge``.

Pure and stdlib-only (no pycryptodome): AES-256-CBC is provided by the
:crypt: module when the Python build ships OpenSSL (CPython does on
every supported platform for >= 3.11 via the ``cryptography``-free
``Crypt`` SPAKE... in practice we use the ``cryptography`` package that
Onyx already depends on).
"""

from __future__ import annotations

import base64
import hashlib
import json
import struct
from dataclasses import dataclass

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

BLOCK_SIZE = 32


class CallbackCryptoError(Exception):
    """Verification/decryption refused the callback; safe to log and 403."""


def _pkcs7_pad(data: bytes) -> bytes:
    pad = BLOCK_SIZE - len(data) % BLOCK_SIZE
    return data + bytes([pad]) * pad


def _pkcs7_unpad(data: bytes) -> bytes:
    if not data:
        raise CallbackCryptoError("empty plaintext")
    pad = data[-1]
    if pad < 1 or pad > BLOCK_SIZE or data[-pad:] != bytes([pad]) * pad:
        raise CallbackCryptoError("bad PKCS7 padding")
    return data[:-pad]


def _aes_cbc_decrypt(key: bytes, encrypted: bytes) -> bytes:
    if len(encrypted) % 16 != 0:
        raise CallbackCryptoError("ciphertext not block aligned")
    decryptor = Cipher(algorithms.AES(key), modes.CBC(key[:16])).decryptor()
    return _pkcs7_unpad(decryptor.update(encrypted) + decryptor.finalize())


def _aes_cbc_encrypt(key: bytes, plaintext: bytes) -> bytes:
    encryptor = Cipher(algorithms.AES(key), modes.CBC(key[:16])).encryptor()
    return encryptor.update(_pkcs7_pad(plaintext)) + encryptor.finalize()


def _unwrap_envelope(plaintext: bytes) -> tuple[str, str]:
    """Split random(16)+len(4)+msg(+suffix) → (msg, suffix)."""
    if len(plaintext) < 20:
        raise CallbackCryptoError("envelope too short")
    msg_len = struct.unpack(">I", plaintext[16:20])[0]
    if 20 + msg_len > len(plaintext):
        raise CallbackCryptoError("envelope length mismatch")
    msg = plaintext[20 : 20 + msg_len]
    suffix = plaintext[20 + msg_len :]
    return msg.decode("utf-8"), suffix.decode("utf-8")


def _wrap_envelope(msg: str, suffix: str) -> bytes:
    msg_bytes = msg.encode("utf-8")
    return (
        b"\x00" * 16  # fixed random block: deterministic re-encryption is fine
        + struct.pack(">I", len(msg_bytes))
        + msg_bytes
        + suffix.encode("utf-8")
    )


# ── WeCom ─────────────────────────────────────────────────────────────────


def wecom_signature(token: str, timestamp: str, nonce: str, encrypt: str) -> str:
    items = sorted([token, timestamp, nonce, encrypt])
    return hashlib.sha1("".join(items).encode("utf-8")).hexdigest()


def wecom_decrypt(encoding_aes_key: str, encrypted_b64: str) -> tuple[str, str]:
    """Decrypt a WeCom callback body → (plaintext_xml_or_json, corp_id)."""
    if len(encoding_aes_key) != 43:
        raise CallbackCryptoError("EncodingAESKey must be 43 chars")
    key = base64.b64decode(encoding_aes_key + "=")
    plaintext = _aes_cbc_decrypt(key, base64.b64decode(encrypted_b64))
    return _unwrap_envelope(plaintext)


def wecom_verify_echo(
    *, token: str, encoding_aes_key: str, signature: str, timestamp: str, nonce: str,
    encrypted_b64: str, corp_id: str,
) -> str:
    """URL verification: check signature, decrypt, confirm corp, return
    the plaintext to echo."""
    expected = wecom_signature(token, timestamp, nonce, encrypted_b64)
    if expected != signature:
        raise CallbackCryptoError("wecom signature mismatch")
    msg, suffix = wecom_decrypt(encoding_aes_key, encrypted_b64)
    if suffix != corp_id:
        raise CallbackCryptoError(f"wecom corp mismatch: {suffix!r}")
    return msg


# ── DingTalk ──────────────────────────────────────────────────────────────


def dingtalk_decrypt(aes_key_b64: str, encrypted_b64: str) -> str:
    key = base64.b64decode(aes_key_b64)
    plaintext = _aes_cbc_decrypt(key, base64.b64decode(encrypted_b64))
    msg, _suffix = _unwrap_envelope(plaintext)
    return msg


def dingtalk_encrypt(aes_key_b64: str, msg: str) -> str:
    key = base64.b64decode(aes_key_b64)
    return base64.b64encode(_aes_cbc_encrypt(key, _wrap_envelope(msg, ""))).decode()


def dingtalk_verify_echo(aes_key_b64: str, encrypted_b64: str) -> str:
    """URL verification: decrypt must yield the literal ``success``; the
    echo response re-encrypts it."""
    msg = dingtalk_decrypt(aes_key_b64, encrypted_b64)
    if msg.strip().strip('"') != "success":
        raise CallbackCryptoError(f"dingtalk verification payload was {msg!r}")
    return dingtalk_encrypt(aes_key_b64, "success")


# ── Feishu ────────────────────────────────────────────────────────────────


def feishu_decrypt(encrypt_key: str, encrypted_b64: str) -> str:
    key = hashlib.sha256(encrypt_key.encode("utf-8")).digest()
    plaintext = _aes_cbc_decrypt(key, base64.b64decode(encrypted_b64))
    msg, _ = _unwrap_envelope(plaintext)
    return msg


def feishu_verify_token(expected_token: str, token: str | None) -> None:
    if not token or token != expected_token:
        raise CallbackCryptoError("feishu verification token mismatch")


@dataclass(frozen=True)
class FeishuEvent:
    type: str
    challenge: str | None = None
    encrypted: str | None = None


def parse_feishu_body(body: dict, encrypt_key: str | None) -> dict:
    """Decrypt when wrapped; verify token for url_verification events."""
    encrypted = body.get("encrypt")
    if isinstance(encrypted, str) and encrypt_key:
        payload = json.loads(feishu_decrypt(encrypt_key, encrypted))
    elif isinstance(encrypted, str):
        raise CallbackCryptoError("feishu event is encrypted but no key configured")
    else:
        payload = body
    return payload
