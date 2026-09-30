"""DingTalk (钉钉) knowledge base connector.

Indexes knowledge base documents through the new DingTalk OpenAPI
(org-level app credentials): lists knowledge bases, their pages, and
fetches page content.

Credentials: ``dingtalk_client_id`` / ``dingtalk_client_secret``.
"""

from __future__ import annotations

from typing import Any

import requests

from onyx.configs.app_configs import INDEX_BATCH_SIZE
from onyx.configs.constants import DocumentSource
from onyx.connectors.china_common import (
    AppTokenManager,
    ChinaConnectorError,
    clean_identifier,
)
from onyx.connectors.interfaces import (
    GenerateDocumentsOutput,
    LoadConnector,
    PollConnector,
    SecondsSinceUnixEpoch,
)
from onyx.connectors.models import (
    ConnectorMissingCredentialError,
    Document,
    TextSection,
)
from onyx.utils.logger import setup_logger

logger = setup_logger()

DING_BASE = "https://api.dingtalk.com"


class DingTalkConnector(LoadConnector, PollConnector):
    def __init__(self, batch_size: int = INDEX_BATCH_SIZE) -> None:
        self.batch_size = batch_size
        self._client_id: str | None = None
        self._client_secret: str | None = None
        self._token: AppTokenManager | None = None

    def load_credentials(self, credentials: dict[str, Any]) -> dict[str, Any] | None:
        self._client_id = credentials["dingtalk_client_id"]
        self._client_secret = credentials["dingtalk_client_secret"]
        self._token = AppTokenManager(self._fetch_token)
        return None

    def _fetch_token(self) -> tuple[str, int]:
        assert self._client_id and self._client_secret
        resp = requests.post(
            f"{DING_BASE}/v1.0/oauth2/accessToken",
            json={
                "appKey": self._client_id,
                "appSecret": self._client_secret,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        token = data.get("accessToken")
        if not token:
            raise ChinaConnectorError(f"DingTalk token error: {data}")
        return str(token), int(data.get("expireIn", 7200))

    def _session(self) -> requests.Session:
        if self._token is None:
            raise ConnectorMissingCredentialError("DingTalk")
        session = requests.Session()
        session.headers["x-acs-dingtalk-access-token"] = self._token.get()
        return session

    def _knowledge_bases(self, session: requests.Session) -> list[dict[str, Any]]:
        resp = session.get(f"{DING_BASE}/v1.0/kb/orgs/knowledgeBases", timeout=30)
        resp.raise_for_status()
        data = resp.json()
        result = data.get("result") or data
        return list(result.get("knowledgeBases") or result or [])

    def _pages(
        self, session: requests.Session, knowledge_base_id: str
    ) -> list[dict[str, Any]]:
        nodes: list[dict[str, Any]] = []
        cursor = 0
        while True:
            resp = session.get(
                f"{DING_BASE}/v1.0/kb/knowledgeBases/{knowledge_base_id}/nodes",
                params={"maxResults": 50, "nextToken": cursor},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            values = data.get("nodes") or data.get("result") or []
            nodes.extend(values)
            next_token = data.get("nextToken")
            if next_token in (None, 0, -1):
                break
            cursor = int(next_token)
        return nodes

    def _page_content(
        self, session: requests.Session, node_id: str
    ) -> str | None:
        resp = session.get(
            f"{DING_BASE}/v1.0/kb/nodes/{node_id}/content",
            timeout=30,
        )
        if resp.status_code != 200:
            logger.warning("DingTalk content %s -> %s", node_id, resp.status_code)
            return None
        data = resp.json()
        content = data.get("content") or (data.get("result") or {}).get("content")
        return str(content) if content else None

    def _load(self, start: float | None = None, end: float | None = None) -> GenerateDocumentsOutput:
        session = self._session()
        batch: list[Document] = []
        for kb in self._knowledge_bases(session):
            kb_id = str(kb.get("knowledgeBaseId") or kb.get("id") or "")
            if not kb_id:
                continue
            kb_name = clean_identifier(str(kb.get("name", "")), kb_id)
            for node in self._pages(session, kb_id):
                node_id = str(node.get("nodeId") or node.get("id") or "")
                if not node_id:
                    continue
                updated = float(node.get("editTime") or node.get("updatedTime") or 0)
                if start is not None and updated < start:
                    continue
                if end is not None and updated >= end:
                    continue
                content = self._page_content(session, node_id)
                if not content:
                    continue
                title = clean_identifier(str(node.get("title", "")), node_id)
                text = f"{title}\n\n{content}"
                batch.append(
                    Document(
                        id=f"dingtalk-kb-{node_id}",
                        source=DocumentSource.DINGTALK,
                        semantic_identifier=f"{kb_name}/{title}",
                        title=title,
                        text=text,
                        sections=[TextSection(text=text)],
                        metadata={"knowledge_base": kb_name},
                        doc_updated_at=updated or None,
                    )
                )
                if len(batch) >= self.batch_size:
                    yield batch
                    batch = []
        if batch:
            yield batch

    def load_from_state(self) -> GenerateDocumentsOutput:
        return self._load()

    def poll_source(
        self, start: SecondsSinceUnixEpoch, end: SecondsSinceUnixEpoch
    ) -> GenerateDocumentsOutput:
        return self._load(start=start, end=end)
