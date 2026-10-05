"""DingTalk (钉钉) todo connector: indexes 待办 tasks.

DingTalk's todo OpenAPI is user-scoped: it lists the todos visible to one
account, addressed by that account's ``unionId``. Configure
``operator_union_id``; the connector indexes that account's todo list.
Org-wide todo indexing depends on a DingTalk capability this API does not
currently expose — until DingTalk ships one, run this connector with an
operator whose todo view is representative, and expect limited coverage.

Credentials: ``dingtalk_client_id`` / ``dingtalk_client_secret``.
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


class DingTalkTodoConnector(LoadConnector, PollConnector):
    def __init__(
        self,
        batch_size: int = INDEX_BATCH_SIZE,
        operator_union_id: str = "",
    ) -> None:
        self.batch_size = batch_size
        self.operator_union_id = operator_union_id
        self._client: DingTalkClient | None = None

    def load_credentials(self, credentials: dict[str, Any]) -> dict[str, Any] | None:
        self._client = DingTalkClient(
            credentials["dingtalk_client_id"], credentials["dingtalk_client_secret"]
        )
        return None

    def _load(
        self, start: float | None = None, end: float | None = None
    ) -> GenerateDocumentsOutput:
        if self._client is None:
            raise ConnectorMissingCredentialError("DingTalk")
        if not self.operator_union_id:
            raise ConnectorMissingCredentialError("DingTalk operator_union_id")
        client = self._client
        # list is invariant: the batch must match the declared
        # `Iterator[list[Document | HierarchyNode]]` yield type.
        batch: list[Document | HierarchyNode] = []
        for task in client.todo_tasks(self.operator_union_id):
            task_id = str(task.get("taskId") or task.get("id") or "")
            if not task_id:
                continue
            updated = float(task.get("modifyTime") or task.get("createTime") or 0)
            if start is not None and updated < start:
                continue
            if end is not None and updated >= end:
                continue
            title = clean_identifier(str(task.get("subject") or ""), task_id)
            description = str(task.get("description") or "").strip()
            text = f"{title}\n\n{description}" if description else title
            detail_url = (task.get("detailUrl") or {}).get("url") or task.get("url")
            batch.append(
                Document(
                    id=f"dingtalk-todo-{task_id}",
                    source=DocumentSource.DINGTALK_TODO,
                    semantic_identifier=title,
                    title=title,
                    sections=[TextSection(text=text, link=detail_url)],
                    metadata={"operator": self.operator_union_id},
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
