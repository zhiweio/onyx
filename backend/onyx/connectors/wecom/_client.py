"""Shared WeCom (企业微信) API client.

One client backs the WeCom connector family (wedrive, approvals): it owns
the corp access-token lifecycle. WeCom passes the token as an
``access_token`` query parameter rather than a header.
"""

from __future__ import annotations

from typing import Any

import requests

from onyx.connectors.china_common import (
    AppTokenManager,
    ChinaConnectorError,
)
from onyx.utils.logger import setup_logger

logger = setup_logger()

WECOM_BASE = "https://qyapi.weixin.qq.com/cgi-bin"


class WeComClient:
    """Corp-token-authenticated WeCom API client."""

    def __init__(self, corp_id: str, corp_secret: str) -> None:
        self._corp_id = corp_id
        self._corp_secret = corp_secret
        self._token = AppTokenManager(self._fetch_corp_token)
        self._session: requests.Session | None = None

    def _fetch_corp_token(self) -> tuple[str, int]:
        resp = requests.get(
            f"{WECOM_BASE}/gettoken",
            params={"corpid": self._corp_id, "corpsecret": self._corp_secret},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("errcode") not in (0, None):
            raise ChinaConnectorError(f"WeCom token error: {data.get('errmsg')}")
        return str(data["access_token"]), int(data.get("expires_in", 7200))

    def session(self) -> requests.Session:
        """One pooled session whose access_token query param always carries
        the current corp token."""
        if self._session is None:
            self._session = requests.Session()
        self._session.params = {"access_token": self._token.get()}  # type: ignore[assignment]
        return self._session

    def post(
        self, path: str, json_body: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        resp = self.session().post(
            f"{WECOM_BASE}/{path.lstrip('/')}", json=json_body, timeout=30
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("errcode") not in (0, None):
            raise ChinaConnectorError(f"WeCom {path} error: {data.get('errmsg')}")
        return data
