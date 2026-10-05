"""DingTalk (钉钉) drive connector: indexes 钉盘 files.

DingTalk's drive APIs act on behalf of a user: every call carries the
``unionId`` of an operator account that can see the target spaces. Configure
``operator_union_id`` and (optionally) ``space_ids`` — by default all org
spaces visible to the operator are indexed. Files are downloaded through a
time-limited CDN URL and parsed by the standard Onyx file extractor.

Credentials: ``dingtalk_client_id`` / ``dingtalk_client_secret``. The app
needs the 钉盘 read capability enabled.

NOTE: response field names are handled defensively (the drive API family
has shifted across API versions); live verification against a real org is
still pending.
"""

from __future__ import annotations

from typing import Any

import requests

from onyx.configs.app_configs import INDEX_BATCH_SIZE
from onyx.configs.constants import DocumentSource
from onyx.connectors.china_common import (
    clean_identifier,
    file_bytes_to_text,
)
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

_MAX_FILE_BYTES = 64 * 1024 * 1024


class DingTalkDriveConnector(LoadConnector, PollConnector):
    def __init__(
        self,
        batch_size: int = INDEX_BATCH_SIZE,
        operator_union_id: str = "",
        space_ids: list[str] | None = None,
    ) -> None:
        self.batch_size = batch_size
        self.operator_union_id = operator_union_id
        self.space_ids = [s for s in (space_ids or []) if s]
        self._client: DingTalkClient | None = None

    def load_credentials(self, credentials: dict[str, Any]) -> dict[str, Any] | None:
        self._client = DingTalkClient(
            credentials["dingtalk_client_id"], credentials["dingtalk_client_secret"]
        )
        return None

    def _client_or_raise(self) -> DingTalkClient:
        if self._client is None:
            raise ConnectorMissingCredentialError("DingTalk")
        return self._client

    def _walk_files(self, client: DingTalkClient) -> list[dict[str, Any]]:
        """Every non-folder entry in the target spaces, with the folder
        path attached as ``_path`` and the space as ``_space``."""
        if not self.operator_union_id:
            raise ConnectorMissingCredentialError("DingTalk operator_union_id")
        spaces = client.drive_spaces(self.operator_union_id)
        if self.space_ids:
            wanted = set(self.space_ids)
            spaces = [
                space
                for space in spaces
                if str(space.get("spaceId") or space.get("id") or "") in wanted
            ]
        files: list[dict[str, Any]] = []
        for space in spaces:
            space_id = str(space.get("spaceId") or space.get("id") or "")
            if not space_id:
                continue
            space_name = str(space.get("spaceName") or space.get("name") or space_id)
            # skip personal drives: without this an operator's own files
            # would leak into the org index
            if str(space.get("spaceType") or "").lower() not in ("org", ""):
                continue
            visited: set[tuple[str, str]] = set()
            queue: list[tuple[str, str]] = [("0", "")]
            while queue:
                parent_id, path = queue.pop(0)
                if (space_id, parent_id) in visited:
                    continue
                visited.add((space_id, parent_id))
                try:
                    entries = client.drive_space_files(
                        space_id, self.operator_union_id, parent_id
                    )
                except Exception:
                    logger.warning(
                        "DingTalk space %s folder %s unreadable; skipping",
                        space_id,
                        parent_id,
                        exc_info=True,
                    )
                    continue
                for item in entries:
                    item_type = str(item.get("type") or item.get("fileType") or "")
                    name = str(item.get("name") or item.get("fileName") or "")
                    item_id = str(item.get("id") or item.get("fileId") or "")
                    if not item_id:
                        continue
                    if item_type == "folder":
                        if (space_id, item_id) not in visited:
                            queue.append((item_id, f"{path}/{name}".strip("/")))
                        continue
                    item["_path"] = path
                    item["_space"] = space_name
                    item["_space_id"] = space_id
                    item["_id"] = item_id
                    files.append(item)
        return files

    @staticmethod
    def _modified_time(item: dict[str, Any]) -> float:
        for key in ("updatedTime", "modifiedTime", "updateTime", "createdTime"):
            if item.get(key):
                return float(item[key])
        return 0.0

    def _file_text(self, client: DingTalkClient, item: dict[str, Any]) -> str | None:
        space_id = str(item.get("_space_id") or "")
        file_id = str(item.get("_id") or "")
        if not space_id or not file_id:
            return None
        url = client.drive_file_download_url(space_id, self.operator_union_id, file_id)
        if not url:
            return None
        try:
            resp = requests.get(url, timeout=120)
        except Exception:
            logger.exception("DingTalk drive download failed: %s", file_id)
            return None
        if resp.status_code != 200 or len(resp.content) > _MAX_FILE_BYTES:
            logger.warning(
                "DingTalk drive download %s -> %s (%s bytes)",
                file_id,
                resp.status_code,
                len(resp.content),
            )
            return None
        name = str(item.get("name") or item.get("fileName") or file_id)
        return file_bytes_to_text(resp.content, name)

    def _item_to_document(self, item: dict[str, Any], text: str) -> Document:
        item_id = str(item.get("_id") or "")
        name = str(item.get("name") or item.get("fileName") or item_id)
        path = str(item.get("_path") or "")
        space_name = str(item.get("_space") or "")
        title = clean_identifier(name, item_id)
        semantic = "/".join(part for part in (space_name, path, title) if part)
        return Document(
            id=f"dingtalk-drive-{item_id}",
            source=DocumentSource.DINGTALK_DRIVE,
            semantic_identifier=semantic,
            title=title,
            sections=[TextSection(text=f"{title}\n\n{text}")],
            metadata={"space": space_name, "folder": path},
            doc_updated_at=self._modified_time(item) or None,
        )

    def _load_documents(
        self, start: float | None = None, end: float | None = None
    ) -> GenerateDocumentsOutput:
        client = self._client_or_raise()
        # list is invariant: the batch must match the declared
        # `Iterator[list[Document | HierarchyNode]]` yield type.
        doc_batch: list[Document | HierarchyNode] = []
        for item in self._walk_files(client):
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
