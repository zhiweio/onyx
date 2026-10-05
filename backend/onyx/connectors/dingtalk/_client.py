"""Shared DingTalk OpenAPI client.

One client backs the DingTalk connector family (knowledge base, drive,
todo): it owns the corp access-token lifecycle and the new-gen OpenAPI
session header.
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

DING_BASE = "https://api.dingtalk.com"


class DingTalkClient:
    """New-gen DingTalk OpenAPI client (x-acs-dingtalk-access-token)."""

    def __init__(self, client_id: str, client_secret: str) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._token = AppTokenManager(self._fetch_token)
        self._session: requests.Session | None = None

    # ── auth ────────────────────────────────────────────────────────────

    def _fetch_token(self) -> tuple[str, int]:
        resp = requests.post(
            f"{DING_BASE}/v1.0/oauth2/accessToken",
            json={"appKey": self._client_id, "appSecret": self._client_secret},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        token = data.get("accessToken")
        if not token:
            raise ChinaConnectorError(f"DingTalk token error: {data}")
        return str(token), int(data.get("expireIn", 7200))

    def session(self) -> requests.Session:
        """One pooled session whose token header always carries the current
        corp access token."""
        if self._session is None:
            self._session = requests.Session()
        self._session.headers["x-acs-dingtalk-access-token"] = self._token.get()
        return self._session

    @staticmethod
    def _numeric_pages(
        fetch_page: Any,
    ) -> list[dict[str, Any]]:
        """DingTalk list APIs page on a numeric nextToken (0 to start, -1
        or missing to end)."""
        items: list[dict[str, Any]] = []
        cursor = 0
        seen: set[int] = set()
        while cursor not in seen:
            seen.add(cursor)
            page_items, next_token = fetch_page(cursor)
            items.extend(page_items)
            if next_token in (None, 0, -1):
                break
            cursor = int(next_token)
        return items

    # ── knowledge base ──────────────────────────────────────────────────

    def knowledge_bases(self) -> list[dict[str, Any]]:
        resp = self.session().get(
            f"{DING_BASE}/v1.0/kb/orgs/knowledgeBases", timeout=30
        )
        resp.raise_for_status()
        data = resp.json()
        result = data.get("result") or data
        return list(result.get("knowledgeBases") or result or [])

    def knowledge_base_nodes(self, knowledge_base_id: str) -> list[dict[str, Any]]:
        def fetch_page(cursor: int) -> tuple[list[dict[str, Any]], Any]:
            resp = self.session().get(
                f"{DING_BASE}/v1.0/kb/knowledgeBases/{knowledge_base_id}/nodes",
                params={"maxResults": 50, "nextToken": cursor},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            values = data.get("nodes") or data.get("result") or []
            return list(values), data.get("nextToken")

        return self._numeric_pages(fetch_page)

    def node_content(self, node_id: str) -> str | None:
        resp = self.session().get(
            f"{DING_BASE}/v1.0/kb/nodes/{node_id}/content", timeout=30
        )
        if resp.status_code != 200:
            logger.warning("DingTalk content %s -> %s", node_id, resp.status_code)
            return None
        data = resp.json()
        content = data.get("content") or (data.get("result") or {}).get("content")
        return str(content) if content else None

    # ── drive (钉盘) ─────────────────────────────────────────────────────

    def drive_spaces(self, union_id: str) -> list[dict[str, Any]]:
        resp = self.session().get(
            f"{DING_BASE}/v1.0/drive/spaces",
            params={"unionId": union_id},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        result = data.get("spaces") or data.get("list") or data.get("result") or []
        return list(result)

    def drive_space_files(
        self, space_id: str, union_id: str, parent_id: str = "0"
    ) -> list[dict[str, Any]]:
        def fetch_page(cursor: int) -> tuple[list[dict[str, Any]], Any]:
            resp = self.session().get(
                f"{DING_BASE}/v1.0/drive/spaces/{space_id}/files",
                params={
                    "unionId": union_id,
                    "parentId": parent_id,
                    "maxResults": 50,
                    "nextToken": cursor,
                },
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            files = data.get("files") or data.get("list") or []
            return list(files), data.get("nextToken")

        return self._numeric_pages(fetch_page)

    def drive_file_download_url(
        self, space_id: str, union_id: str, file_id: str
    ) -> str | None:
        resp = self.session().get(
            f"{DING_BASE}/v1.0/drive/spaces/{space_id}/files/{file_id}/downloadUrl",
            params={"unionId": union_id},
            timeout=30,
        )
        if resp.status_code != 200:
            logger.warning("DingTalk download url %s -> %s", file_id, resp.status_code)
            return None
        data = resp.json()
        url = data.get("downloadUrl") or (data.get("result") or {}).get("downloadUrl")
        return str(url) if url else None

    # ── todo (待办) ──────────────────────────────────────────────────────

    def todo_tasks(self, union_id: str) -> list[dict[str, Any]]:
        def fetch_page(cursor: int) -> tuple[list[dict[str, Any]], Any]:
            resp = self.session().get(
                f"{DING_BASE}/v1.0/todo/users/{union_id}/tasks",
                params={"maxResults": 50, "nextToken": cursor},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            items = data.get("taskList") or data.get("tasks") or data.get("list") or []
            return list(items), data.get("nextToken")

        return self._numeric_pages(fetch_page)
