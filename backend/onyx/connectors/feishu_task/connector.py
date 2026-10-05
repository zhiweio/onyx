"""Feishu (Lark) task connector: indexes task lists and tasks (task v2).

One document per task. Participants (creator, executors, followers) become
the document ACL via contact email resolution; tasks whose participants
cannot be read fall back to a restrictive (empty, private) ACL.

Credentials: ``feishu_app_id`` / ``feishu_app_secret``. The app needs the
task read scope.
"""

from __future__ import annotations

from typing import Any

from onyx.access.models import ExternalAccess
from onyx.configs.app_configs import INDEX_BATCH_SIZE
from onyx.configs.constants import DocumentSource
from onyx.connectors.china_common import ChinaConnectorError, clean_identifier
from onyx.connectors.exceptions import (
    CredentialInvalidError,
    InsufficientPermissionsError,
    UnexpectedValidationError,
)
from onyx.connectors.feishu._client import FeishuClient
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

_ROLE_LABELS = {"executor": "负责", "follower": "关注", "creator": "创建"}


def _ms_to_seconds(value: Any) -> float:
    try:
        return float(value) / 1000.0 if value else 0.0
    except (TypeError, ValueError):
        return 0.0


class FeishuTaskConnector(SlimConnectorWithPermSync, LoadConnector, PollConnector):
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
        """Bad app credentials and missing task read scope are the two
        misconfigurations a test call can detect."""
        client = self._client_or_raise()
        try:
            client.session()
        except ChinaConnectorError as e:
            raise CredentialInvalidError(f"Invalid Feishu app credentials: {e}") from e
        except Exception as e:
            raise UnexpectedValidationError(
                f"Unexpected error while validating Feishu task settings: {e}"
            ) from e
        try:
            client.task_tasklists()
        except ChinaConnectorError as e:
            raise InsufficientPermissionsError(
                "Feishu rejected the task list; confirm the app has the task "
                f"read scope: {e}"
            ) from e
        except Exception as e:
            raise UnexpectedValidationError(
                f"Unexpected error while validating Feishu task settings: {e}"
            ) from e

    # ── indexing ─────────────────────────────────────────────────────────

    def _task_text(self, client: FeishuClient, task: dict[str, Any]) -> str:
        lines = [str(task.get("summary") or "").strip()]
        description = str(task.get("description") or "").strip()
        if description:
            lines.append(description)
        status = task.get("status") or {}
        lines.append("状态: 已完成" if status.get("is_completed") else "状态: 进行中")
        due = task.get("due") or {}
        due_date = _ms_to_seconds(due.get("date"))
        if due_date:
            lines.append(f"截止: {due_date}")
        members = self._task_members(client, task)
        if members:
            lines.append("参与人:")
            for name, role in members:
                lines.append(f"  {role}: {name}")
        return "\n".join(line for line in lines if line)

    def _task_members(
        self, client: FeishuClient, task: dict[str, Any]
    ) -> list[tuple[str, str]]:
        """(label, role) pairs; ids resolved to emails where possible."""
        pairs: list[tuple[str, str]] = []
        for member in task.get("members") or []:
            role = _ROLE_LABELS.get(str(member.get("role") or ""), "参与")
            member_id = str((member.get("id") or ""))
            if not member_id:
                continue
            email = client.user_email(member_id)
            pairs.append((email or f"user-{member_id[-6:]}", role))
        return pairs

    def _task_to_document(
        self, client: FeishuClient, tasklist_name: str, task: dict[str, Any]
    ) -> Document:
        guid = str(task.get("guid") or "")
        title = clean_identifier(str(task.get("summary") or ""), guid)
        updated = _ms_to_seconds(task.get("updated_at"))
        return Document(
            id=f"feishu-task-{guid}",
            source=DocumentSource.FEISHU_TASK,
            semantic_identifier=f"{tasklist_name}/{title}",
            title=title,
            sections=[
                TextSection(text=self._task_text(client, task), link=task.get("url"))
            ],
            metadata={
                "tasklist": tasklist_name,
                "status": "completed"
                if (task.get("status") or {}).get("is_completed")
                else "active",
            },
            doc_updated_at=updated or None,
        )

    def _load_documents(
        self, start: float | None = None, end: float | None = None
    ) -> GenerateDocumentsOutput:
        client = self._client_or_raise()
        # list is invariant: the batch must match the declared
        # `Iterator[list[Document | HierarchyNode]]` yield type.
        doc_batch: list[Document | HierarchyNode] = []
        for tasklist in client.task_tasklists():
            tasklist_guid = str(tasklist.get("guid") or "")
            if not tasklist_guid:
                continue
            tasklist_name = clean_identifier(
                str(tasklist.get("name") or ""), tasklist_guid
            )
            for task in client.tasklist_tasks(tasklist_guid):
                if not task.get("guid"):
                    continue
                updated = _ms_to_seconds(task.get("updated_at"))
                if start is not None and updated < start:
                    continue
                if end is not None and updated >= end:
                    continue
                doc_batch.append(self._task_to_document(client, tasklist_name, task))
                if len(doc_batch) >= self.batch_size:
                    yield doc_batch
                    doc_batch = []
        if doc_batch:
            yield doc_batch

    def load_from_state(self) -> GenerateDocumentsOutput:
        return self._load_documents()

    def poll_source(
        self, start: SecondsSinceUnixEpoch, end: SecondsSinceUnixEpoch
    ) -> GenerateDocumentsOutput:
        return self._load_documents(start=start, end=end)

    # ── permission sync ──────────────────────────────────────────────────

    def _task_external_access(
        self, client: FeishuClient, task: dict[str, Any]
    ) -> ExternalAccess:
        """Participants → ExternalAccess; unreadable tasks yield the
        restrictive empty/private fallback."""
        try:
            members = task.get("members")
            if members is None:
                detail = client.task_detail(str(task.get("guid") or ""))
                members = (detail or {}).get("members") if detail else None
            emails: set[str] = set()
            for member in members or []:
                member_id = str(member.get("id") or "")
                if not member_id:
                    continue
                email = client.user_email(member_id)
                if email:
                    emails.add(email)
        except Exception:
            logger.warning(
                "Feishu task members unreadable for %s; using private ACL",
                task.get("guid"),
                exc_info=True,
            )
            return ExternalAccess.empty()
        return ExternalAccess(
            external_user_emails=emails, external_user_group_ids=set(), is_public=False
        )

    def retrieve_all_slim_docs_perm_sync(
        self,
        start: SecondsSinceUnixEpoch | None = None,
        end: SecondsSinceUnixEpoch | None = None,
        callback: Any = None,
    ) -> GenerateSlimDocumentOutput:
        """Walk the same task lists the indexer walks and emit one
        SlimDocument per task with its participants.

        Time filters are ignored on purpose: permission sync wants full
        coverage regardless of edit recency."""
        del start, end, callback
        client = self._client_or_raise()
        # list is invariant: the batch must match the declared
        # `Iterator[list[SlimDocument | HierarchyNode]]` yield type.
        batch: list[SlimDocument | HierarchyNode] = []
        for tasklist in client.task_tasklists():
            tasklist_guid = str(tasklist.get("guid") or "")
            if not tasklist_guid:
                continue
            for task in client.tasklist_tasks(tasklist_guid):
                guid = str(task.get("guid") or "")
                if not guid:
                    continue
                batch.append(
                    SlimDocument(
                        id=f"feishu-task-{guid}",
                        external_access=self._task_external_access(client, task),
                    )
                )
                if len(batch) >= self.batch_size:
                    yield batch
                    batch = []
        if batch:
            yield batch
