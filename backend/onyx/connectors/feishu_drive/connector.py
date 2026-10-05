"""Feishu (Lark) drive connector: indexes cloud-drive folders.

Walks drive folders (BFS from the configured roots, default: the app's own
root folder). Online docs (docx) come from the raw-content API; sheets and
bitables are exported to CSV through export tasks; uploaded files are
downloaded and parsed by the standard Onyx file extractor. Mindnotes and
shortcuts are skipped.

Per-file ACLs sync through ``retrieve_all_slim_docs_perm_sync`` using the
drive permission-member API; unreadable members fall back to a restrictive
(empty, private) ACL.

Credentials: ``feishu_app_id`` / ``feishu_app_secret``. The app needs the
drive read scope, and every folder to index must be inside the app's
access range.
"""

from __future__ import annotations

from typing import Any

from onyx.configs.app_configs import INDEX_BATCH_SIZE
from onyx.configs.constants import DocumentSource
from onyx.connectors.china_common import (
    ChinaConnectorError,
    clean_identifier,
    file_bytes_to_text,
)
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

# Online docs whose text we can extract, mapped to their export format
# (docx uses raw_content; sheet/bitable go through export tasks to CSV).
_ONLINE_DOC_EXPORTS = {"sheet": "csv", "bitable": "csv"}
_PERM_TYPE_BY_FILE_TYPE = {
    "docx": "docx",
    "doc": "docx",
    "sheet": "sheet",
    "bitable": "bitable",
}


class FeishuDriveConnector(SlimConnectorWithPermSync, LoadConnector, PollConnector):
    def __init__(
        self,
        batch_size: int = INDEX_BATCH_SIZE,
        root_folder_tokens: list[str] | None = None,
    ) -> None:
        self.batch_size = batch_size
        self.root_folder_tokens = [t for t in (root_folder_tokens or []) if t]
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
        """Bad app credentials (token rejected) and missing drive read scope
        are the two misconfigurations a test call can detect."""
        client = self._client_or_raise()
        try:
            client.session()
        except ChinaConnectorError as e:
            raise CredentialInvalidError(f"Invalid Feishu app credentials: {e}") from e
        except Exception as e:
            raise UnexpectedValidationError(
                f"Unexpected error while validating Feishu drive settings: {e}"
            ) from e
        try:
            self._roots(client)
        except ChinaConnectorError as e:
            raise InsufficientPermissionsError(
                "Feishu rejected the drive folder listing; confirm the app has "
                "the drive read scope and the folders are inside the app's "
                f"availability range: {e}"
            ) from e
        except Exception as e:
            raise UnexpectedValidationError(
                f"Unexpected error while validating Feishu drive settings: {e}"
            ) from e

    def _roots(self, client: FeishuClient) -> list[tuple[str, str]]:
        """(folder_token, path) start points; defaults to the app root."""
        if self.root_folder_tokens:
            return [(token, "") for token in self.root_folder_tokens]
        root = client.drive_root_folder_token()
        if not root:
            raise ChinaConnectorError("Feishu returned an empty root folder token")
        return [(root, "")]

    def _walk_files(self, client: FeishuClient) -> list[dict[str, Any]]:
        """Every non-folder entry under the roots, with the folder path
        attached as ``_path``. Folder cycles are guarded by token set."""
        files: list[dict[str, Any]] = []
        visited: set[str] = set()
        queue = self._roots(client)
        while queue:
            folder_token, path = queue.pop(0)
            if folder_token in visited:
                continue
            visited.add(folder_token)
            for item in client.drive_folder_files(folder_token):
                item_type = str(item.get("type") or "")
                name = str(item.get("name") or "")
                if item_type == "folder":
                    child_token = str(item.get("token") or "")
                    if child_token and child_token not in visited:
                        queue.append((child_token, f"{path}/{name}".strip("/")))
                    continue
                item["_path"] = path
                files.append(item)
        return files

    @staticmethod
    def _modified_time(item: dict[str, Any]) -> float:
        for key in ("modified_time", "mtime", "created_time"):
            if item.get(key):
                return float(item[key])
        return 0.0

    def _file_text(self, client: FeishuClient, item: dict[str, Any]) -> str | None:
        token = str(item["token"])
        item_type = str(item.get("type") or "file")
        name = str(item.get("name") or token)
        if item_type == "docx":
            raw = client.docx_raw_content(token)
            return strip_html(raw).strip() if raw else None
        if item_type in _ONLINE_DOC_EXPORTS:
            data = client.drive_export_bytes(
                token, item_type, _ONLINE_DOC_EXPORTS[item_type]
            )
            if data is None:
                return None
            return data.decode("utf-8", errors="replace")
        content = client.drive_media_download(token)
        if not content:
            return None
        return file_bytes_to_text(content, name)

    def _item_to_document(self, item: dict[str, Any], text: str) -> Document:
        token = str(item["token"])
        name = str(item.get("name") or token)
        path = str(item.get("_path") or "")
        title = clean_identifier(name, token)
        semantic = f"{path}/{title}".strip("/") if path else title
        modified = self._modified_time(item)
        return Document(
            id=f"feishu-drive-{token}",
            source=DocumentSource.FEISHU_DRIVE,
            semantic_identifier=semantic,
            title=title,
            sections=[TextSection(text=f"{title}\n\n{text}", link=item.get("url"))],
            metadata={"folder": path, "obj_type": str(item.get("type") or "file")},
            doc_updated_at=modified or None,
        )

    def _load_documents(
        self, start: float | None = None, end: float | None = None
    ) -> GenerateDocumentsOutput:
        client = self._client_or_raise()
        # list is invariant: the batch must match the declared
        # `Iterator[list[Document | HierarchyNode]]` yield type.
        doc_batch: list[Document | HierarchyNode] = []
        for item in self._walk_files(client):
            if str(item.get("type")) == "shortcut":
                continue
            modified = self._modified_time(item)
            if start is not None and modified < start:
                continue
            if end is not None and modified >= end:
                continue
            text = self._file_text(client, item)
            if not text:
                continue
            doc_batch.append(self._item_to_document(item, text))
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

    def _indexable_type(self, item: dict[str, Any]) -> str | None:
        item_type = str(item.get("type") or "")
        if item_type in ("docx", "doc", "sheet", "bitable"):
            return item_type
        if item_type == "file":
            return "file"
        return None

    def retrieve_all_slim_docs_perm_sync(
        self,
        start: SecondsSinceUnixEpoch | None = None,
        end: SecondsSinceUnixEpoch | None = None,
        callback: Any = None,
    ) -> GenerateSlimDocumentOutput:
        """Walk the same tree the indexer walks and emit one SlimDocument
        per indexable file with its drive permission members.

        Time filters are ignored on purpose: permission sync wants full
        coverage regardless of edit recency."""
        del start, end, callback
        client = self._client_or_raise()
        # list is invariant: the batch must match the declared
        # `Iterator[list[SlimDocument | HierarchyNode]]` yield type.
        batch: list[SlimDocument | HierarchyNode] = []
        for item in self._walk_files(client):
            perm_type = self._indexable_type(item)
            if perm_type is None:
                continue
            token = str(item["token"])
            batch.append(
                SlimDocument(
                    id=f"feishu-drive-{token}",
                    external_access=client.token_external_access(token, perm_type),
                )
            )
            if len(batch) >= self.batch_size:
                yield batch
                batch = []
        if batch:
            yield batch
