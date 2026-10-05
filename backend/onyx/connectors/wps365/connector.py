"""WPS365 connector: indexes cloud documents via the WPS open API.

Lists files from the cloud drive (file list API), downloads each one, and
parses it with the standard Onyx file extractor (pdf/docx/xlsx/pptx/html
plus text). Base URL is configurable per deployment region.

Credentials: ``wps365_client_id`` / ``wps365_client_secret`` /
optional ``wps365_base_url`` (default https://open.wps.cn).

NOTE: the list API is called defensively with an optional parent folder
filter; folder traversal coverage depends on the tenant's API version and
still needs live verification.
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
from onyx.utils.logger import setup_logger

logger = setup_logger()

DEFAULT_BASE = "https://open.wps.cn"
_MAX_FILE_BYTES = 64 * 1024 * 1024


class WPS365Connector(LoadConnector, PollConnector):
    def __init__(
        self,
        batch_size: int = INDEX_BATCH_SIZE,
        parent_file_id: str = "",
    ) -> None:
        self.batch_size = batch_size
        self.parent_file_id = parent_file_id
        self._client_id: str | None = None
        self._client_secret: str | None = None
        self._base = DEFAULT_BASE
        self._token: AppTokenManager | None = None

    def load_credentials(self, credentials: dict[str, Any]) -> dict[str, Any] | None:
        self._client_id = credentials["wps365_client_id"]
        self._client_secret = credentials["wps365_client_secret"]
        self._base = str(credentials.get("wps365_base_url") or DEFAULT_BASE).rstrip("/")
        self._token = AppTokenManager(self._fetch_token)
        return None

    def _fetch_token(self) -> tuple[str, int]:
        assert self._client_id and self._client_secret
        resp = requests.post(
            f"{self._base}/oauthapi/v3/inner/company/token",
            data={
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "grant_type": "company_token",
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        token = data.get("company_access_token") or data.get("access_token")
        if not token:
            raise ChinaConnectorError(f"WPS365 token error: {data}")
        return str(token), int(data.get("expires_in", 3600))

    def _session(self) -> requests.Session:
        if self._token is None:
            raise ConnectorMissingCredentialError("WPS365")
        session = requests.Session()
        session.headers["Authorization"] = f"Bearer {self._token.get()}"
        return session

    def _list_files(self, session: requests.Session) -> list[dict[str, Any]]:
        files: list[dict[str, Any]] = []
        offset = 0
        while True:
            params: dict[str, Any] = {"offset": offset, "limit": 100}
            if self.parent_file_id:
                params["parent_id"] = self.parent_file_id
            resp = session.get(
                f"{self._base}/openapi/file/wpscloud/v1/files",
                params=params,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            items = data.get("files") or data.get("data") or []
            files.extend(items)
            if len(items) < 100:
                return files
            offset += 100

    def _download(self, session: requests.Session, file_id: str) -> bytes | None:
        resp = session.get(
            f"{self._base}/openapi/file/wpscloud/v1/files/{file_id}/download",
            timeout=120,
        )
        if resp.status_code != 200:
            logger.warning("WPS365 download %s -> %s", file_id, resp.status_code)
            return None
        return resp.content

    @staticmethod
    def _file_name(item: dict[str, Any]) -> str:
        return str(item.get("name") or item.get("file_name") or "")

    @staticmethod
    def _file_id(item: dict[str, Any]) -> str:
        return str(item.get("file_id") or item.get("id") or "")

    @staticmethod
    def _modified_time(item: dict[str, Any]) -> float:
        for key in ("modify_time", "mtime", "update_time", "create_time"):
            if item.get(key):
                return float(item[key])
        return 0.0

    def _load(
        self, start: float | None = None, end: float | None = None
    ) -> GenerateDocumentsOutput:
        session = self._session()
        # list is invariant: the batch must match the declared
        # `Iterator[list[Document | HierarchyNode]]` yield type.
        batch: list[Document | HierarchyNode] = []
        for item in self._list_files(session):
            file_id = self._file_id(item)
            name = self._file_name(item)
            if not file_id or not name:
                continue
            updated = self._modified_time(item)
            if start is not None and updated < start:
                continue
            if end is not None and updated >= end:
                continue
            content = self._download(session, file_id)
            if not content:
                continue
            if len(content) > _MAX_FILE_BYTES:
                logger.warning("WPS365 file %s too large; skipping", file_id)
                continue
            text = file_bytes_to_text(content, name)
            if not text:
                continue
            title = clean_identifier(name, file_id)
            batch.append(
                Document(
                    id=f"wps365-{file_id}",
                    source=DocumentSource.WPS365,
                    semantic_identifier=title,
                    title=title,
                    sections=[TextSection(text=f"{title}\n\n{text}")],
                    metadata={"wps365_file": name},
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
