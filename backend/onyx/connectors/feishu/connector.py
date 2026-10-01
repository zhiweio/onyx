"""Feishu (Lark) connector: wiki spaces + cloud documents.

Indexes wiki pages (spaces → node tree) and docx documents from My Space
root folders, using the app's tenant_access_token. Only content the app
can read is indexed; per-document ACL sync rides the permission-sync
framework in a later milestone (content-only until then).

Credentials: ``feishu_app_id`` / ``feishu_app_secret``.
"""

from __future__ import annotations

import re
from typing import Any

import requests

from onyx.configs.app_configs import INDEX_BATCH_SIZE
from onyx.configs.constants import DocumentSource
from onyx.connectors.china_common import (
    AppTokenManager,
    ChinaConnectorError,
    clean_identifier,
    get_json,
    paginated,
    post_json,
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
    HierarchyNode,
    TextSection,
)
from onyx.utils.logger import setup_logger

logger = setup_logger()

FEISHU_BASE = "https://open.feishu.cn/open-apis"
_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    return _TAG_RE.sub("", text)


class FeishuConnector(LoadConnector, PollConnector):
    def __init__(self, batch_size: int = INDEX_BATCH_SIZE) -> None:
        self.batch_size = batch_size
        self._app_id: str | None = None
        self._app_secret: str | None = None
        self._token: AppTokenManager | None = None

    def load_credentials(self, credentials: dict[str, Any]) -> dict[str, Any] | None:
        self._app_id = credentials["feishu_app_id"]
        self._app_secret = credentials["feishu_app_secret"]
        self._token = AppTokenManager(self._fetch_tenant_token)
        return None

    def _fetch_tenant_token(self) -> tuple[str, int]:
        assert self._app_id and self._app_secret
        data = post_json(
            requests.Session(),
            f"{FEISHU_BASE}/auth/v3/tenant_access_token/internal",
            json_body={"app_id": self._app_id, "app_secret": self._app_secret},
        )
        if data.get("code") not in (0, None):
            raise ChinaConnectorError(f"Feishu token error: {data.get('msg')}")
        return str(data["tenant_access_token"]), int(data.get("expire", 7200))

    def _session(self) -> requests.Session:
        if self._token is None:
            raise ConnectorMissingCredentialError("Feishu")
        session = requests.Session()
        token = self._token.get()
        session.headers.update({"Authorization": f"Bearer {token}"})
        return session

    # ── wiki ─────────────────────────────────────────────────────────────

    def _wiki_spaces(self, session: requests.Session) -> list[dict[str, Any]]:
        def page(page_token: str | None) -> tuple[list[dict[str, Any]], str | None]:
            params: dict[str, Any] = {"page_size": 50}
            if page_token:
                params["page_token"] = page_token
            data = get_json(session, f"{FEISHU_BASE}/wiki/v2/spaces", params=params)
            if data.get("code") not in (0, None):
                raise ChinaConnectorError(f"Feishu spaces error: {data.get('msg')}")
            spaces = data.get("data") or {}
            return list(spaces.get("items") or []), spaces.get("page_token")

        return list(paginated(page))

    def _wiki_nodes(
        self, session: requests.Session, space_id: str
    ) -> list[dict[str, Any]]:
        def page(page_token: str | None) -> tuple[list[dict[str, Any]], str | None]:
            params: dict[str, Any] = {"page_size": 50}
            if page_token:
                params["page_token"] = page_token
            data = get_json(
                session,
                f"{FEISHU_BASE}/wiki/v2/spaces/{space_id}/nodes",
                params=params,
            )
            if data.get("code") not in (0, None):
                raise ChinaConnectorError(f"Feishu nodes error: {data.get('msg')}")
            payload = data.get("data") or {}
            return list(payload.get("items") or []), payload.get("page_token")

        return list(paginated(page))

    def _docx_raw_content(
        self, session: requests.Session, document_id: str
    ) -> str | None:
        data = get_json(
            session, f"{FEISHU_BASE}/docx/v1/documents/{document_id}/raw_content"
        )
        if data.get("code") not in (0, None):
            logger.warning("Feishu raw_content %s: %s", document_id, data.get("msg"))
            return None
        content = (data.get("data") or {}).get("content")
        return str(content) if content else None

    def _load_documents(
        self, start: float | None = None, end: float | None = None
    ) -> GenerateDocumentsOutput:
        session = self._session()
        # list is invariant: the batch must match the declared
        # `Iterator[list[Document | HierarchyNode]]` yield type.
        doc_batch: list[Document | HierarchyNode] = []

        for space in self._wiki_spaces(session):
            space_name = clean_identifier(str(space.get("name", "")), "space")
            for node in self._wiki_nodes(session, str(space["space_id"])):
                obj_type = node.get("obj_type")
                if obj_type not in ("docx", "doc"):
                    continue
                edited = float(node.get("node_edit_time") or 0)
                if start is not None and edited < start:
                    continue
                if end is not None and edited >= end:
                    continue
                content = self._docx_raw_content(session, str(node["obj_token"]))
                if not content:
                    continue
                doc_batch.append(self._node_to_document(node, space_name, content))
                if len(doc_batch) >= self.batch_size:
                    yield doc_batch
                    doc_batch = []
        if doc_batch:
            yield doc_batch

    def _node_to_document(
        self, node: dict[str, Any], space_name: str, content: str
    ) -> Document:
        title = clean_identifier(str(node.get("title", "")), str(node["obj_token"]))
        doc_id = f"feishu-wiki-{node['obj_token']}"
        text = f"{title}\n\n{_strip_html(content).strip()}"
        node_edit_time = node.get("node_edit_time")
        return Document(
            id=doc_id,
            source=DocumentSource.FEISHU,
            semantic_identifier=f"{space_name}/{title}",
            title=title,
            sections=[TextSection(text=text, link=node.get("url"))],
            metadata={"space": space_name, "obj_type": "docx"},
            doc_updated_at=float(node_edit_time) if node_edit_time else None,
        )

    def load_from_state(self) -> GenerateDocumentsOutput:
        return self._load_documents()

    def poll_source(
        self, start: SecondsSinceUnixEpoch, end: SecondsSinceUnixEpoch
    ) -> GenerateDocumentsOutput:
        return self._load_documents(start=start, end=end)
