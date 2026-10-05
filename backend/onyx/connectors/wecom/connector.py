"""WeCom (企业微信) wedrive connector: indexes 微盘 files.

Walks wedrive spaces → folder trees with the corp access token; downloads
every file and parses it with the standard Onyx file extractor (pdf/docx/
xlsx/pptx/html plus text). Uses the documented wedrive API family
(space_list / file_list / file_download).

Credentials: ``wecom_corp_id`` / ``wecom_corp_secret`` (same app as SSO
if desired; wedrive API permission required).
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
from onyx.connectors.wecom._client import WECOM_BASE, WeComClient
from onyx.utils.logger import setup_logger

logger = setup_logger()

_MAX_FILE_BYTES = 64 * 1024 * 1024
# 微盘 file_type: 2 marks a folder (1/3+ are files of various kinds).
_FOLDER_FILE_TYPE = "2"


class WeComConnector(LoadConnector, PollConnector):
    def __init__(self, batch_size: int = INDEX_BATCH_SIZE) -> None:
        self.batch_size = batch_size
        self._client: WeComClient | None = None

    def load_credentials(self, credentials: dict[str, Any]) -> dict[str, Any] | None:
        self._client = WeComClient(
            credentials["wecom_corp_id"], credentials["wecom_corp_secret"]
        )
        return None

    def _client_or_raise(self) -> WeComClient:
        if self._client is None:
            raise ConnectorMissingCredentialError("WeCom")
        return self._client

    # ── wedrive listing ──────────────────────────────────────────────────

    def _spaces(self, client: WeComClient) -> list[dict[str, Any]]:
        spaces: list[dict[str, Any]] = []
        offset = 0
        while True:
            data = client.post("/wedrive/space_list", {"offset": offset, "limit": 50})
            page = data.get("space_list") or []
            spaces.extend(page)
            next_offset = data.get("next")
            if not page or next_offset in (None, 0):
                break
            offset = int(next_offset)
        return spaces

    def _space_files(
        self, client: WeComClient, space_id: str, father_id: str
    ) -> list[dict[str, Any]]:
        files: list[dict[str, Any]] = []
        start = 0
        while True:
            data = client.post(
                "/wedrive/file_list",
                {
                    "spaceid": space_id,
                    "fatherid": father_id,
                    "sort_type": 1,
                    "start": start,
                    "limit": 100,
                },
            )
            page = data.get("file_list") or []
            files.extend(page)
            if len(page) < 100:
                return files
            start += 100

    def _walk_files(self, client: WeComClient) -> list[dict[str, Any]]:
        """Every file under every space, with the folder path attached as
        ``_path`` and the space as ``_space``."""
        files: list[dict[str, Any]] = []
        for space in self._spaces(client):
            space_id = str(space.get("spaceid") or space.get("space_id") or "")
            if not space_id:
                continue
            space_name = clean_identifier(str(space.get("space_name") or ""), space_id)
            visited: set[tuple[str, str]] = set()
            queue: list[tuple[str, str]] = [("0", "")]
            while queue:
                father_id, path = queue.pop(0)
                if (space_id, father_id) in visited:
                    continue
                visited.add((space_id, father_id))
                try:
                    entries = self._space_files(client, space_id, father_id)
                except Exception:
                    logger.warning(
                        "WeCom space %s folder %s unreadable; skipping",
                        space_id,
                        father_id,
                        exc_info=True,
                    )
                    continue
                for item in entries:
                    item_id = str(item.get("fileid") or item.get("file_id") or "")
                    if not item_id:
                        continue
                    name = str(item.get("file_name") or item.get("filename") or "")
                    file_type = str(item.get("file_type") or item.get("type") or "")
                    if file_type == _FOLDER_FILE_TYPE:
                        if (space_id, item_id) not in visited:
                            queue.append((item_id, f"{path}/{name}".strip("/")))
                        continue
                    item["_path"] = path
                    item["_space"] = space_name
                    item["_id"] = item_id
                    files.append(item)
        return files

    @staticmethod
    def _modified_time(item: dict[str, Any]) -> float:
        for key in ("update_time", "updated_time", "create_time"):
            if item.get(key):
                return float(item[key])
        return 0.0

    def _file_text(self, client: WeComClient, item: dict[str, Any]) -> str | None:
        file_id = str(item.get("_id") or "")
        try:
            resp = client.session().post(
                f"{WECOM_BASE}/wedrive/file_download",
                json={"fileid": file_id},
                timeout=120,
            )
        except Exception:
            logger.exception("WeCom download failed: %s", file_id)
            return None
        if resp.status_code != 200 or not resp.content:
            logger.warning("WeCom download %s -> %s", file_id, resp.status_code)
            return None
        # The download API answers with the raw file for small files and a
        # JSON body carrying a temp download_url for larger ones.
        if resp.content[:1] == b"{":
            try:
                payload = resp.json()
            except ValueError:
                payload = {}
            url = payload.get("download_url")
            if not url:
                logger.warning("WeCom download %s returned no url", file_id)
                return None
            resp = requests.get(str(url), timeout=120)
            if resp.status_code != 200:
                return None
        if len(resp.content) > _MAX_FILE_BYTES:
            logger.warning("WeCom file %s too large; skipping", file_id)
            return None
        name = str(item.get("file_name") or item.get("filename") or file_id)
        return file_bytes_to_text(resp.content, name)

    def _item_to_document(self, item: dict[str, Any], text: str) -> Document:
        item_id = str(item.get("_id") or "")
        name = str(item.get("file_name") or item.get("filename") or item_id)
        path = str(item.get("_path") or "")
        space_name = str(item.get("_space") or "")
        title = clean_identifier(name, item_id)
        semantic = "/".join(part for part in (space_name, path, title) if part)
        return Document(
            id=f"wecom-wedrive-{item_id}",
            source=DocumentSource.WECOM,
            semantic_identifier=semantic,
            title=title,
            sections=[TextSection(text=f"{title}\n\n{text}")],
            metadata={"space": space_name, "folder": path},
            doc_updated_at=self._modified_time(item) or None,
        )

    def _load(
        self, start: float | None = None, end: float | None = None
    ) -> GenerateDocumentsOutput:
        client = self._client_or_raise()
        # list is invariant: the batch must match the declared
        # `Iterator[list[Document | HierarchyNode]]` yield type.
        batch: list[Document | HierarchyNode] = []
        for item in self._walk_files(client):
            updated = self._modified_time(item)
            if start is not None and updated < start:
                continue
            if end is not None and updated >= end:
                continue
            text = self._file_text(client, item)
            if not text:
                continue
            batch.append(self._item_to_document(item, text))
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
