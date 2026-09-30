"""WeCom (企业微信) wedrive connector: indexes text files from wedrive.

Uses the app's corp access token. Files are downloaded through the
wedrive download API; only text-decodable files are indexed.

Credentials: ``wecom_corp_id`` / ``wecom_corp_secret`` (same app as SSO
if desired; wedrive API permission required).
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
    get_json,
    paginated,
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

WECOM_BASE = "https://qyapi.weixin.qq.com/cgi-bin"
_TEXT_SUFFIXES = (
    ".txt", ".md", ".csv", ".json", ".xml", ".log", ".yml", ".yaml", ".html", ".py", ".js"
)


class WeComConnector(LoadConnector, PollConnector):
    def __init__(self, batch_size: int = INDEX_BATCH_SIZE) -> None:
        self.batch_size = batch_size
        self._corp_id: str | None = None
        self._corp_secret: str | None = None
        self._token: AppTokenManager | None = None

    def load_credentials(self, credentials: dict[str, Any]) -> dict[str, Any] | None:
        self._corp_id = credentials["wecom_corp_id"]
        self._corp_secret = credentials["wecom_corp_secret"]
        self._token = AppTokenManager(self._fetch_corp_token)
        return None

    def _fetch_corp_token(self) -> tuple[str, int]:
        assert self._corp_id and self._corp_secret
        data = get_json(
            requests.Session(),
            f"{WECOM_BASE}/gettoken",
            params={"corpid": self._corp_id, "corpsecret": self._corp_secret},
        )
        if data.get("errcode") not in (0, None):
            raise ChinaConnectorError(f"WeCom token error: {data.get('errmsg')}")
        return str(data["access_token"]), int(data.get("expires_in", 7200))

    def _session(self) -> requests.Session:
        if self._token is None:
            raise ConnectorMissingCredentialError("WeCom")
        session = requests.Session()
        session.params = {"access_token": self._token.get()}  # type: ignore[assignment]
        return session

    def _list_files(self, session: requests.Session) -> list[dict[str, Any]]:
        def page(cursor: str | None) -> tuple[list[dict[str, Any]], str | None]:
            body: dict[str, Any] = {"filter": 0}
            if cursor:
                body["cursor"] = cursor
            resp = session.post(
                f"{WECOM_BASE}/wedrive/list", json=body, timeout=30
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("errcode") not in (0, None):
                raise ChinaConnectorError(f"WeCom list error: {data.get('errmsg')}")
            payload = data.get("file_list") or {}
            return list(payload.get("file_list") or []), payload.get("next_cursor")

        return list(paginated(page))

    def _download(self, session: requests.Session, file_id: str) -> bytes | None:
        resp = session.post(
            f"{WECOM_BASE}/wedrive/download", json={"fileid": file_id}, timeout=60
        )
        if resp.status_code != 200:
            logger.warning("WeCom download %s -> %s", file_id, resp.status_code)
            return None
        return resp.content

    def _load(self, start: float | None = None, end: float | None = None) -> GenerateDocumentsOutput:
        session = self._session()
        batch: list[Document] = []
        for item in self._list_files(session):
            name = str(item.get("file_name") or "")
            if not name.lower().endswith(_TEXT_SUFFIXES):
                continue
            updated = float(item.get("update_time") or 0)
            if start is not None and updated < start:
                continue
            if end is not None and updated >= end:
                continue
            content = self._download(session, str(item["file_id"]))
            if not content:
                continue
            try:
                text = content.decode("utf-8")
            except UnicodeDecodeError:
                continue
            title = clean_identifier(name, str(item["file_id"]))
            batch.append(
                Document(
                    id=f"wecom-wedrive-{item['file_id']}",
                    source=DocumentSource.WECOM,
                    semantic_identifier=title,
                    title=title,
                    text=text,
                    sections=[TextSection(text=text)],
                    metadata={"wedrive_file": name},
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
