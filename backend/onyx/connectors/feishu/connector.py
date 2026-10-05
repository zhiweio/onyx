"""Feishu (Lark) wiki connector: indexes wiki spaces and their docx pages.

Walks wiki spaces → node trees with the app's tenant_access_token. Only
content the app can read is indexed. Per-document ACLs sync through
``retrieve_all_slim_docs_perm_sync``: wiki member lists → external user
emails (contact lookup) + external group ids; docs whose members cannot be
read fall back to a restrictive (empty, private) ACL.

Credentials: ``feishu_app_id`` / ``feishu_app_secret``.
"""

from __future__ import annotations

from typing import Any

from onyx.configs.app_configs import INDEX_BATCH_SIZE
from onyx.configs.constants import DocumentSource
from onyx.connectors.china_common import ChinaConnectorError, clean_identifier
from onyx.connectors.exceptions import (
    CredentialInvalidError,
    InsufficientPermissionsError,
    UnexpectedValidationError,
)
from onyx.connectors.feishu._client import FeishuClient, strip_html
from onyx.connectors.interfaces import (
    GenerateDocumentsOutput,
    GenerateSlimDocumentOutput,
    LoadConnector,
    PollConnector,
    SecondsSinceUnixEpoch,
    SlimConnectorWithPermSync,
)
from onyx.connectors.models import (
    ConnectorMissingCredentialError,
    Document,
    HierarchyNode,
    SlimDocument,
    TextSection,
)
from onyx.utils.logger import setup_logger

logger = setup_logger()


class FeishuConnector(SlimConnectorWithPermSync, LoadConnector, PollConnector):
    def __init__(self, batch_size: int = INDEX_BATCH_SIZE) -> None:
        self.batch_size = batch_size
        self._client: FeishuClient | None = None

    def load_credentials(self, credentials: dict[str, Any]) -> dict[str, Any] | None:
        self._client = FeishuClient(
            credentials["feishu_app_id"], credentials["feishu_app_secret"]
        )
        return None

    def _client_or_raise(self) -> FeishuClient:
        if self._client is None:
            raise ConnectorMissingCredentialError("Feishu")
        return self._client

    def validate_connector_settings(self) -> None:
        """Surface the two misconfigurations a test call can detect: bad app
        credentials (token request rejected) and missing wiki read scope."""
        client = self._client_or_raise()
        try:
            client.session()
        except ChinaConnectorError as e:
            raise CredentialInvalidError(f"Invalid Feishu app credentials: {e}") from e
        except Exception as e:
            raise UnexpectedValidationError(
                f"Unexpected error while validating Feishu settings: {e}"
            ) from e
        try:
            client.wiki_spaces()
        except ChinaConnectorError as e:
            raise InsufficientPermissionsError(
                "Feishu rejected the wiki space list; confirm the app has the "
                "wiki read scope and the wiki is inside the app's availability "
                f"range: {e}"
            ) from e
        except Exception as e:
            raise UnexpectedValidationError(
                f"Unexpected error while validating Feishu settings: {e}"
            ) from e

    # ── indexing ─────────────────────────────────────────────────────────

    def _load_documents(
        self, start: float | None = None, end: float | None = None
    ) -> GenerateDocumentsOutput:
        client = self._client_or_raise()
        # list is invariant: the batch must match the declared
        # `Iterator[list[Document | HierarchyNode]]` yield type.
        doc_batch: list[Document | HierarchyNode] = []

        for space in client.wiki_spaces():
            space_name = clean_identifier(str(space.get("name", "")), "space")
            for node in client.wiki_nodes(str(space["space_id"])):
                obj_type = node.get("obj_type")
                if obj_type not in ("docx", "doc"):
                    continue
                edited = float(node.get("node_edit_time") or 0)
                if start is not None and edited < start:
                    continue
                if end is not None and edited >= end:
                    continue
                content = client.docx_raw_content(str(node["obj_token"]))
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
        text = f"{title}\n\n{strip_html(content).strip()}"
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

    # ── permission sync ──────────────────────────────────────────────────

    def retrieve_all_slim_docs_perm_sync(
        self,
        start: SecondsSinceUnixEpoch | None = None,
        end: SecondsSinceUnixEpoch | None = None,
        callback: Any = None,
    ) -> GenerateSlimDocumentOutput:
        """Walk the same wiki tree the indexer walks and emit one
        SlimDocument per docx page carrying its external access.

        Time filters are ignored on purpose: permission sync wants full
        coverage regardless of edit recency."""
        del start, end, callback
        client = self._client_or_raise()
        # list is invariant: the batch must match the declared
        # `Iterator[list[SlimDocument | HierarchyNode]]` yield type.
        batch: list[SlimDocument | HierarchyNode] = []

        for space in client.wiki_spaces():
            for node in client.wiki_nodes(str(space["space_id"])):
                if node.get("obj_type") not in ("docx", "doc"):
                    continue
                token = str(node["obj_token"])
                batch.append(
                    SlimDocument(
                        id=f"feishu-wiki-{token}",
                        external_access=client.token_external_access(token, "wiki"),
                    )
                )
                if len(batch) >= self.batch_size:
                    yield batch
                    batch = []
        if batch:
            yield batch
