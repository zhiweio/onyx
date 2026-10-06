"""DingTalk (钉钉) knowledge base connector.

Indexes wiki workspaces through the new DingTalk OpenAPI (org-level app
credentials): lists workspaces, walks each node tree, and assembles
document text from the doc-suite block list. The wiki APIs act on behalf
of a user, so credentials include that user's unionId.

Credentials: ``dingtalk_client_id`` / ``dingtalk_client_secret`` /
``dingtalk_operator_union_id``.
"""

from __future__ import annotations

from typing import Any

from onyx.configs.app_configs import INDEX_BATCH_SIZE
from onyx.configs.constants import DocumentSource
from onyx.connectors.china_common import clean_identifier
from onyx.connectors.dingtalk._client import DingTalkClient
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


class DingTalkConnector(LoadConnector, PollConnector):
    def __init__(self, batch_size: int = INDEX_BATCH_SIZE) -> None:
        self.batch_size = batch_size
        self._client: DingTalkClient | None = None

    def load_credentials(self, credentials: dict[str, Any]) -> dict[str, Any] | None:
        self._client = DingTalkClient(
            credentials["dingtalk_client_id"],
            credentials["dingtalk_client_secret"],
            credentials.get("dingtalk_operator_union_id"),
        )
        return None

    def _load(
        self, start: float | None = None, end: float | None = None
    ) -> GenerateDocumentsOutput:
        if self._client is None:
            raise ConnectorMissingCredentialError("DingTalk")
        client = self._client
        # list is invariant, so the batch must match the declared
        # `Iterator[list[Document | HierarchyNode]]` yield type.
        batch: list[Document | HierarchyNode] = []
        for workspace in client.knowledge_bases():
            kb_id = str(workspace.get("workspaceId") or workspace.get("id") or "")
            root_node_id = str(workspace.get("rootNodeId") or "")
            if not kb_id or not root_node_id:
                continue
            kb_name = clean_identifier(str(workspace.get("name", "")), kb_id)
            for node in client.knowledge_base_nodes(root_node_id):
                node_id = str(node.get("nodeId") or node.get("id") or "")
                if not node_id:
                    continue
                # v2 wiki timestamps are epoch milliseconds.
                updated = float(node.get("modifiedTimestamp") or 0) / 1000
                if start is not None and updated < start:
                    continue
                if end is not None and updated >= end:
                    continue
                content = client.node_content(node_id)
                if not content:
                    continue
                title = clean_identifier(str(node.get("name", "")), node_id)
                text = f"{title}\n\n{content}"
                batch.append(
                    Document(
                        id=f"dingtalk-kb-{node_id}",
                        source=DocumentSource.DINGTALK,
                        semantic_identifier=f"{kb_name}/{title}",
                        title=title,
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
