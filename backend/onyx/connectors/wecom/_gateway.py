"""WeCom smart-robot CLI gateway client, shared by the gateway connectors.

The gateway (``https://qyapi.weixin.qq.com/cli``) authenticates with the
smart robot's ``bot_id``/``bot_secret``: a signed bootstrap call returns a
short-lived bearer token sent as ``Authorization`` on every request. JSON
bodies ride a flat envelope — HTTP 200 with ``{"errcode", "errmsg",
"results_json"}`` where ``results_json`` nests the business result as
(doubly) serialized JSON. This client unwraps it and caches the token.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import time
from typing import Any

import requests

from onyx.connectors.china_common import AppTokenManager, ChinaConnectorError
from onyx.utils.logger import setup_logger

logger = setup_logger()

WECOM_GATEWAY_BASE = "https://qyapi.weixin.qq.com/cli"
_WECOM_TOKEN_URL = "https://qyapi.weixin.qq.com/cgi-bin/aibot/cli/get_cli_config"

# errcode 853004/853005 mean the cached token died (expired or rotated);
# one re-fetch and retry is the documented recovery.
_TOKEN_RETRY_ERRCODES = {853004, 853005}


class WeComGatewayClient:
    """Bearer-token client over the CLI gateway's payload-string envelope."""

    def __init__(self, bot_id: str, bot_secret: str) -> None:
        self._bot_id = bot_id
        self._bot_secret = bot_secret
        self._session = requests.Session()
        self._token_manager = AppTokenManager(
            fetch=self._fetch_token,
            # The bootstrap response carries no expires_in; re-derive on this
            # cadence (the gateway answers 853004/853005 for a dead token).
            refresh_margin_seconds=0,
        )
        self._token_ttl_seconds = 3000
        # The manager re-fetches when `expires_at - now <= margin`; with
        # margin 0 that is only after expiry, so track the TTL ourselves.
        self._token_issued_at = 0.0

    def _fetch_token(self) -> tuple[str, int]:
        now = int(time.time())
        nonce = f"onyx_{int(time.time() * 1000)}_{secrets.token_hex(4)}"
        signature = hashlib.sha256(
            f"{self._bot_secret}{self._bot_id}{now}{nonce}".encode()
        ).hexdigest()
        response = self._session.post(
            _WECOM_TOKEN_URL,
            json={
                "bot_id": self._bot_id,
                "time": now,
                "nonce": nonce,
                "signature": signature,
                "bind_source": 1,
            },
            timeout=30,
        )
        if response.status_code >= 400:
            raise ChinaConnectorError(
                f"WeCom token bootstrap failed: HTTP {response.status_code}"
            )
        data = response.json()
        if data.get("errcode") not in (None, 0):
            raise ChinaConnectorError(
                f"WeCom token bootstrap rejected (errcode={data.get('errcode')}): "
                f"{data.get('errmsg')}"
            )
        token = data.get("token")
        if not token:
            raise ChinaConnectorError("WeCom token bootstrap returned no token")
        return str(token), self._token_ttl_seconds

    def _unwrap(self, value: Any) -> Any:
        """Peel the gateway's nested-JSON layers: results_json (str) →
        {"result": str|obj} → result → possibly another JSON string."""
        for _ in range(4):
            if isinstance(value, str):
                try:
                    value = json.loads(value)
                except ValueError:
                    return value
            if isinstance(value, dict) and set(value) == {"result"}:
                value = value["result"]
                continue
            return value
        return value

    def _post_envelope(
        self,
        path: str,
        body: dict[str, Any],
        extra_headers: dict[str, str] | None = None,
    ) -> tuple[int, str, Any]:
        """One envelope POST: ``(errcode, errmsg, unwrapped_result)``; raises
        ``ChinaConnectorError`` on transport failure."""
        response = self._session.post(
            WECOM_GATEWAY_BASE + path,
            json=body,
            timeout=60,
            headers={
                "Authorization": f"Bearer {self._token_manager.get()}",
                **(extra_headers or {}),
            },
        )
        if response.status_code >= 400:
            raise ChinaConnectorError(
                f"WeCom gateway {path} failed: HTTP {response.status_code}"
            )
        envelope = response.json()
        errcode = envelope.get("errcode")
        if errcode not in (None, 0):
            return int(errcode or 0), str(envelope.get("errmsg") or ""), None
        result = self._unwrap(envelope.get("results_json"))
        inner = result if isinstance(result, dict) else {}
        return 0, "", inner

    def _poll_long_task(
        self, path: str, taskid: str, poll_mode: int, max_polls: int = 60
    ) -> Any:
        """Drain a long-task (``poll_mode``) response.

        The gateway runs two poll protocols (mirrors the official CLI's
        transport): mode 0 re-POSTs ``/task/query`` with the flat
        ``PollClawLongTask`` body; mode 1 re-POSTs the *original* endpoint
        with an empty JSON body and the taskid in ``X-Long-Poll-TaskId``.
        """
        poll_body = {
            "payload": json.dumps(
                {
                    "method": "PollClawLongTask",
                    "payload": json.dumps({"taskid": taskid}),
                }
            )
        }
        for _ in range(max_polls):
            if poll_mode == 1:
                errcode, errmsg, inner = self._post_envelope(
                    path, {}, extra_headers={"X-Long-Poll-TaskId": taskid}
                )
            else:
                errcode, errmsg, inner = self._post_envelope("/task/query", poll_body)
            if errcode:
                raise ChinaConnectorError(
                    f"WeCom task poll rejected (errcode={errcode}): {errmsg}"
                )
            # Termination: long_task_poll.done wins over taskid presence —
            # mode-1 rounds keep returning the SAME taskid while done flips.
            poll_state = inner.get("long_task_poll") or {}
            if poll_state.get("done"):
                # Mode 0: the terminal wrapper carries the result separately.
                return self._unwrap(inner.get("result"))
            if not inner.get("taskid"):
                # Mode 1: the terminal response body is the final payload.
                return self._unwrap(inner)
            taskid = str(inner["taskid"])
            time.sleep(float(poll_state.get("polling_interval_ms") or 1000) / 1000.0)
        raise ChinaConnectorError(f"WeCom long task {taskid[:16]} polling timed out")

    def call(self, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        """One gateway call (``path`` gateway-relative, e.g.
        ``/doc/search``); returns the unwrapped business result. Responses
        that defer to a long task (``taskid``) are polled to completion
        transparently."""
        body = {"payload": json.dumps(payload or {}, ensure_ascii=False)}
        for attempt in (1, 2):
            errcode, errmsg, result = self._post_envelope(path, body)
            if errcode in _TOKEN_RETRY_ERRCODES and attempt == 1:
                self._token_manager.invalidate()
                continue
            if errcode:
                raise ChinaConnectorError(
                    f"WeCom gateway {path} rejected (errcode={errcode}): {errmsg}"
                )
            taskid = result.get("taskid")
            if taskid:
                poll_mode = int(result.get("poll_mode") or 0)
                result = self._unwrap(
                    self._poll_long_task(path, str(taskid), poll_mode)
                )
            if isinstance(result, dict):
                # Server-injected prompt blocks are platform metadata.
                result.pop("security_notice", None)
                result.pop("extra_identity_context", None)
            return result if isinstance(result, dict) else {}
        raise ChinaConnectorError(f"WeCom gateway {path} failed after token refresh")

    def iter_pages(
        self,
        path: str,
        payload: dict[str, Any],
        cursor_field: str = "cursor",
        max_pages: int = 100,
    ) -> Any:
        """Yield the items of a cursor-paginated gateway list call. The
        response must carry the list plus ``has_more``/``next_cursor``; the
        items key is whatever list the response contains."""
        cursor: str | None = None
        seen: set[str] = set()
        for _ in range(max_pages):
            request = dict(payload)
            if cursor:
                request[cursor_field] = cursor
            page = self.call(path, request)
            yield page
            if not page.get("has_more"):
                return
            next_cursor = page.get("next_cursor")
            if not next_cursor or next_cursor in seen:
                if next_cursor:
                    logger.warning(
                        "WeCom pagination cursor repeated at %s; stopping", path
                    )
                return
            seen.add(str(next_cursor))
            cursor = str(next_cursor)
