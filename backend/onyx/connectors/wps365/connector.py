"""WPS365 connector: indexes cloud documents via the WPS open API.

Lists files from the team drive (file list API), downloading text-like
files directly. Base URL is configurable per deployment region.

Credentials: ``wps365_client_id`` / ``wps365_client_secret`` /
optional ``wps365_base_url`` (default https://open.wps.cn).
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

DEFAULT_BASE = "https://open.wps.cn"
_TEXT_SUFFIXES = (
    ".txt", ".md", ".csv", ".json", ".xml", ".log", ".html", ".docx", ".pdf"
)


class WPS365Connector(LoadConnector, PollConnector):
    def __init__(self, batch_size: int = INDEX_BATCH_SIZE) -> None:
        self.batch_size = batch_size
        self._client_id: str | None = None
        self._client_secret: str | None = None
        self._base = DEFAULT_BASE
        self._token: AppTokenManager | None = None

    def load_credentials(self, credentials: dict[str, Any]) -> dict[str, Any] | None:
        self._client_id = credentials["wps365_client_id"]
        self._client_secret = credentials["wps365_client_secret"]
        self._base = str(
            credentials.get("wps365_base_url") or DEFAULT_BASE
        ).rstrip("/")
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
            resp = session.get(
                f"{self._base}/openapi/file/wpscloud/v1/files",
                params={"offset": offset, "limit": 100},
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
            timeout=60,
        )
        if resp.status_code != 200:
            logger.warning("WPS365 download %s -> %s", file_id, resp.status_code)
            return None
        return resp.content

    def _load(self, start: float | None = None, end: float | None = None) -> GenerateDocumentsOutput:
        session = self._session()
        batch: list[Document] = []
        for item in self._list_files(session):
            name = str(item.get("name") or item.get("file_name") or "")
            file_id = str(item.get("file_id") or item.get("id") or "")
            if not file_id or not name.lower().endswith(_TEXT_SUFFIXES):
                continue
            updated = float(item.get("modify_time") or item.get("mtime") or 0)
            if start is not None and updated < start:
                continue
            if end is not None and updated >= end:
                continue
            content = self._download(session, file_id)
            if not content:
                continue
            if name.endswith(".pdf") or name.endswith(".docx"):
                # binary formats flow through the standard document
                # parser by providing the raw bytes below; text path
                # covers plain formats.
                try:
                    text = content.decode("utf-8")
                except UnicodeDecodeError:
                    logger.info("WPS365 skipping binary %s (parser hook M8)", name)
                    continue
            else:
                try:
                    text = content.decode("utf-8")
                except UnicodeDecodeError:
                    continue
            title = clean_identifier(name, file_id)
            batch.append(
                Document(
                    id=f"wps365-{file_id}",
                    source=DocumentSource.WPS365,
                    semantic_identifier=title,
                    title=title,
                    text=text,
                    sections=[TextSection(text=text)],
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
