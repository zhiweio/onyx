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

# Doc-suite block types whose payload carries the visible text under "text".
_TEXT_BLOCK_TYPES = (
    "paragraph",
    "heading",
    "unorderedList",
    "orderedList",
    "todo",
    "quote",
    "codeBlock",
)


def _blocks_to_text(blocks: list[dict[str, Any]]) -> str | None:
    """Flatten a doc-suite block list into plain text.

    Top-level blocks may nest further blocks (e.g. ``columns.children``),
    so extraction recurses and preserves document order by block index.
    """

    def block_text(block: dict[str, Any]) -> str:
        parts: list[str] = []
        block_type = str(block.get("blockType") or "")
        payload = block.get(block_type)
        if block_type in _TEXT_BLOCK_TYPES and isinstance(payload, dict):
            text = str(payload.get("text") or "")
            if block_type == "heading":
                level = str(payload.get("level") or "")
                depth = int(level.rsplit("-", 1)[-1]) if level[-1:].isdigit() else 1
                text = f"{'#' * depth} {text}".strip()
            if text:
                parts.append(text)
        # Nested containers (e.g. columns) hold lists of block lists.
        children = block.get("children")
        if isinstance(children, list):
            for group in children:
                if isinstance(group, list):
                    parts.extend(
                        block_text(child) for child in group if isinstance(child, dict)
                    )
                elif isinstance(group, dict):
                    parts.append(block_text(group))
        return "\n".join(p for p in parts if p)

    ordered = sorted(blocks, key=lambda b: int(b.get("index") or 0))
    lines = [block_text(b) for b in ordered]
    text = "\n\n".join(line for line in lines if line)
    return text or None


class DingTalkClient:
    """New-gen DingTalk OpenAPI client (x-acs-dingtalk-access-token)."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        operator_union_id: str | None = None,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        # The wiki (knowledge base) APIs act on behalf of a user; their
        # operatorId parameter is the user's unionId.
        self._operator_union_id = operator_union_id or None
        self._token = AppTokenManager(self._fetch_token)
        self._session: requests.Session | None = None

    @property
    def operator_union_id(self) -> str | None:
        return self._operator_union_id

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

    # ── knowledge base (wiki) ───────────────────────────────────────────

    def knowledge_bases(self) -> list[dict[str, Any]]:
        """List wiki workspaces visible to the operator user.

        Each workspace carries ``workspaceId``, ``name`` and ``rootNodeId``;
        the node tree is walked from the root node downward.
        """
        resp = self.session().get(
            f"{DING_BASE}/v2.0/wiki/workspaces",
            params={"operatorId": self._require_operator()},
            timeout=30,
        )
        resp.raise_for_status()
        return list(resp.json().get("workspaces") or [])

    def knowledge_base_nodes(self, root_node_id: str) -> list[dict[str, Any]]:
        """All FILE nodes under a workspace root node (breadth-first)."""
        nodes: list[dict[str, Any]] = []
        visited: set[str] = set()
        queue = [root_node_id]
        while queue:
            parent_id = queue.pop(0)
            if parent_id in visited:
                continue
            visited.add(parent_id)
            children = self._wiki_child_nodes(parent_id)
            for child in children:
                if str(child.get("type") or "") == "FOLDER":
                    queue.append(str(child.get("nodeId") or ""))
                else:
                    nodes.append(child)
        return nodes

    def _wiki_child_nodes(self, parent_node_id: str) -> list[dict[str, Any]]:
        children: list[dict[str, Any]] = []
        next_token: str | None = None
        for _ in range(100):
            params: dict[str, Any] = {
                "operatorId": self._require_operator(),
                "parentNodeId": parent_node_id,
                "maxResults": 50,
            }
            if next_token:
                params["nextToken"] = next_token
            resp = self.session().get(
                f"{DING_BASE}/v2.0/wiki/nodes", params=params, timeout=30
            )
            resp.raise_for_status()
            data = resp.json()
            children.extend(data.get("nodes") or [])
            next_token = data.get("nextToken")
            # DingTalk ends paging with a missing token or the -1 sentinel.
            if not next_token or str(next_token) in ("0", "-1"):
                break
        return children

    def node_content(self, node_id: str) -> str | None:
        """Document text assembled from the doc-suite block list."""
        blocks: list[dict[str, Any]] = []
        start_index = 0
        seen_starts: set[int] = set()
        while start_index not in seen_starts:
            seen_starts.add(start_index)
            resp = self.session().get(
                f"{DING_BASE}/v1.0/doc/suites/documents/{node_id}/blocks",
                params={
                    "operatorId": self._require_operator(),
                    "startIndex": start_index,
                    "endIndex": start_index + 199,
                },
                timeout=30,
            )
            if resp.status_code != 200:
                logger.warning("DingTalk content %s -> %s", node_id, resp.status_code)
                return None
            data = resp.json().get("result") or {}
            page = list(data.get("data") or [])
            if not page:
                break
            blocks.extend(page)
            max_index = max(int(b.get("index") or 0) for b in page)
            if max_index < start_index + 199:
                break
            start_index = max_index + 1
        return _blocks_to_text(blocks)

    def _require_operator(self) -> str:
        if not self._operator_union_id:
            raise ChinaConnectorError(
                "DingTalk knowledge base APIs require an operator unionId; "
                "set dingtalk_operator_union_id in the connector credentials"
            )
        return self._operator_union_id

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
