"""Shared plumbing for China workplace connectors.

These platforms share three traits: app-level tokens (tenant/corp) that
expire and must be cached, page-token pagination on every list API, and
documents whose text needs a dedicated export call. This module holds
that plumbing once so each connector stays a thin protocol description.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Iterator

import requests

from onyx.utils.logger import setup_logger

logger = setup_logger()


class ChinaConnectorError(Exception):
    """Platform API refused the call; message is operator-readable."""


@dataclass
class AppToken:
    access_token: str
    expires_at: float  # unix seconds


class AppTokenManager:
    """Fetches and caches an app-level access token until shortly before
    expiry. Thread-safe enough for the celery worker pattern (single
    fetch loop per connector instance); on races the loser's token is
    simply overwritten with an equivalent one.
    """

    def __init__(
        self,
        fetch: Callable[[], tuple[str, int]],
        refresh_margin_seconds: int = 120,
    ) -> None:
        self._fetch = fetch
        self._refresh_margin = refresh_margin_seconds
        self._token: AppToken | None = None

    def get(self) -> str:
        now = time.time()
        if self._token is None or self._token.expires_at - now <= self._refresh_margin:
            token, expires_in = self._fetch()
            self._token = AppToken(
                access_token=token, expires_at=now + float(expires_in)
            )
        return self._token.access_token

    def invalidate(self) -> None:
        self._token = None


def paginated(
    fetch_page: Callable[[str | None], tuple[list[dict[str, Any]], str | None]],
    max_pages: int = 1000,
) -> Iterator[dict[str, Any]]:
    """Iterate a page-token API until it stops returning a next token.

    ``fetch_page(page_token)`` returns (items, next_page_token); iteration
    ends when next is None/empty or the page cap is hit (runaway guard).
    A repeated next token also ends iteration: some platforms (Feishu)
    keep emitting a cursor on the final page, and honoring it forever
    would loop until the API rejects the stale cursor.
    """
    page_token: str | None = None
    seen_tokens: set[str] = set()
    pages = 0
    while pages < max_pages:
        items, next_token = fetch_page(page_token)
        yield from items
        pages += 1
        if not next_token or next_token in seen_tokens:
            if next_token:
                logger.warning(
                    "pagination cursor %s repeated; stopping to avoid a loop",
                    next_token[:32],
                )
            return
        seen_tokens.add(next_token)
        page_token = next_token
    logger.warning("pagination cap (%s pages) hit; stopping early", max_pages)


def _http_error(resp: requests.Response) -> ChinaConnectorError:
    """Turn a non-2xx response that still carries a JSON error body (the
    normal style for Chinese platform APIs) into a readable error."""
    try:
        data = resp.json()
    except Exception:
        data = {}
    code = data.get("code", data.get("errcode"))
    msg = data.get("msg", data.get("errmsg")) or resp.text[:200]
    if code is not None or msg:
        return ChinaConnectorError(f"HTTP {resp.status_code} (code={code}): {msg}")
    return ChinaConnectorError(f"HTTP {resp.status_code}")


def get_json(session: requests.Session, url: str, **kwargs: Any) -> dict[str, Any]:
    resp = session.get(url, timeout=30, **kwargs)
    if resp.status_code >= 400:
        raise _http_error(resp)
    return resp.json()


def post_json(
    session: requests.Session,
    url: str,
    *,
    json_body: dict[str, Any] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    resp = session.post(url, json=json_body, timeout=30, **kwargs)
    if resp.status_code >= 400:
        raise _http_error(resp)
    return resp.json()


def fetch_text_or_none(
    session: requests.Session, url: str, **kwargs: Any
) -> str | None:
    """Fetch a text export, returning None (and logging) on any failure so
    one bad document never sinks the indexing batch."""
    try:
        resp = session.get(url, timeout=60, **kwargs)
        if resp.status_code != 200:
            logger.warning("text fetch %s -> %s", url, resp.status_code)
            return None
        return resp.text
    except Exception:
        logger.exception("text fetch failed: %s", url)
        return None


def clean_identifier(name: str, fallback: str) -> str:
    name = (name or "").strip()
    return name if name else fallback


def file_bytes_to_text(content: bytes, file_name: str) -> str | None:
    """Decode downloaded file bytes to text through the standard Onyx file
    parser (pdf/docx/xlsx/pptx/html). Falls back to a strict UTF-8/GBK
    decode for plain text (also covers environments where the parser stack
    is unavailable). Returns None when nothing readable comes out, so one
    bad download never sinks the indexing batch."""
    from io import BytesIO

    from onyx.file_processing.extract_file_text import extract_file_text

    try:
        text = extract_file_text(
            BytesIO(content), file_name, break_on_unprocessable=False
        )
    except Exception:
        logger.exception("file text extraction failed: %s", file_name)
        text = None
    if text and text.strip():
        return text
    for encoding in ("utf-8", "gbk"):
        try:
            decoded = content.decode(encoding)
        except UnicodeDecodeError:
            continue
        # NUL bytes mean binary content that merely happened to decode
        if decoded.strip() and "\x00" not in decoded:
            return decoded
    return None
