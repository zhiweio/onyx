"""WeCom (企业微信) docs connector: indexes online documents via the
smart-robot CLI gateway.

Discovery is keyword- or id-driven — the gateway exposes no "list all
documents" operation. Configure either explicit ``doc_ids``, ``keywords``
(each keyword paginated through ``doc/search``), or both. Content is fetched
per document type: Word docs as markdown, spreadsheets as CSV per worksheet,
smartsheets as record lines, smartpages as page text.

The gateway authorizes as the smart robot acting for its authorized human,
and exposes no per-document viewer list, so these documents carry no
external ACL — visibility is governed by the connector-credential pair's
access_type.

Credentials: ``wecom_bot_id`` / ``wecom_bot_secret`` (智能机器人 Bot ID/Secret).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from onyx.configs.app_configs import INDEX_BATCH_SIZE
from onyx.configs.constants import DocumentSource
from onyx.connectors.china_common import ChinaConnectorError
from onyx.connectors.exceptions import (
    CredentialInvalidError,
    InsufficientPermissionsError,
    UnexpectedValidationError,
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
from onyx.connectors.wecom._gateway import WeComGatewayClient
from onyx.utils.logger import setup_logger

logger = setup_logger()

_CST = timezone(timedelta(hours=8))
_MAX_SHEETS_PER_DOC = 10
_MAX_SMARTSHEET_ROWS = 500
_SEARCH_MAX_PAGES = 20
_DOC_TYPES = ("doc", "sheet", "smartsheet", "smartpage")


def _parse_cst(value: Any) -> float | None:
    """``YYYY-MM-DD HH:mm:ss`` (CST wall clock) → unix seconds, or None."""
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return (
            datetime.strptime(raw, "%Y-%m-%d %H:%M:%S").replace(tzinfo=_CST).timestamp()
        )
    except ValueError:
        return None


class WeComDocsConnector(LoadConnector, PollConnector):
    def __init__(
        self,
        batch_size: int = INDEX_BATCH_SIZE,
        doc_ids: list[str] | None = None,
        keywords: list[str] | None = None,
    ) -> None:
        self.batch_size = batch_size
        self.doc_ids = [d for d in (doc_ids or []) if d]
        self.keywords = [k for k in (keywords or []) if k]
        self._client: WeComGatewayClient | None = None

    def load_credentials(self, credentials: dict[str, Any]) -> dict[str, Any] | None:
        self._client = WeComGatewayClient(
            credentials["wecom_bot_id"], credentials["wecom_bot_secret"]
        )
        return None

    def _client_or_raise(self) -> WeComGatewayClient:
        if self._client is None:
            raise ConnectorMissingCredentialError("WeCom")
        return self._client

    def validate_connector_settings(self) -> None:
        """A token bootstrap failure means bad bot credentials; a rejected
        discovery call means the robot lacks gateway access."""
        client = self._client_or_raise()
        try:
            client.call("/service/discovery", {})
        except ChinaConnectorError as e:
            message = str(e)
            if "token bootstrap" in message or "errcode=" in message:
                raise CredentialInvalidError(
                    f"Invalid WeCom bot credentials: {e}"
                ) from e
            raise InsufficientPermissionsError(
                f"WeCom gateway rejected the call; confirm the smart robot is "
                f"configured with API mode enabled: {e}"
            ) from e
        except Exception as e:
            raise UnexpectedValidationError(
                f"Unexpected error while validating WeCom docs settings: {e}"
            ) from e

    # ── discovery ────────────────────────────────────────────────────────

    def _discover_docs(self, client: WeComGatewayClient) -> list[dict[str, Any]]:
        """The docs to index as ``{docid, doc_name, doc_type, modify_time}``
        records: explicit ids first, then keyword search hits (deduped)."""
        found: dict[str, dict[str, Any]] = {}
        for doc_id in self.doc_ids:
            found[str(doc_id)] = {"docid": str(doc_id)}
        for keyword in self.keywords:
            pages = 0
            for page in client.iter_pages("/doc/search", {"keywords": [keyword]}):
                pages += 1
                for info in page.get("docs") or []:
                    if not isinstance(info, dict):
                        continue
                    docid = str(info.get("docid") or "")
                    if docid:
                        found.setdefault(docid, info)
                if pages >= _SEARCH_MAX_PAGES:
                    logger.warning("WeCom doc search cap hit for keyword %r", keyword)
                    break
        return list(found.values())

    # ── content extraction, per doc_type ─────────────────────────────────

    def _doc_text(self, client: WeComGatewayClient, docid: str) -> str | None:
        try:
            result = client.call(
                "/doc/contents/get", {"docid": docid, "content_type": "markdown"}
            )
        except ChinaConnectorError:
            logger.warning("WeCom doc %s unreadable", docid, exc_info=True)
            return None
        content = result.get("content")
        if isinstance(content, str) and content.strip():
            return content
        # Overlong content lands in a server-side file we cannot read; the
        # search snippet (if any) stands in.
        logger.info("WeCom doc %s content served as file; using fallback", docid)
        return None

    def _sheet_text(self, client: WeComGatewayClient, docid: str) -> str | None:
        try:
            meta = client.call("/sheet/get", {"docid": docid})
        except ChinaConnectorError:
            logger.warning("WeCom sheet %s unreadable", docid, exc_info=True)
            return None
        lines: list[str] = []
        for sheet in (meta.get("sheets") or [])[:_MAX_SHEETS_PER_DOC]:
            if not isinstance(sheet, dict):
                continue
            sheet_id = str(sheet.get("sheet_id") or "")
            title = str(sheet.get("title") or sheet_id)
            if not sheet_id:
                continue
            try:
                data = client.call(
                    "/sheet/ranges/get",
                    {"docid": docid, "sheet_id": sheet_id, "mode": "csv"},
                )
            except ChinaConnectorError:
                logger.warning("WeCom sheet %s/%s range read failed", docid, sheet_id)
                continue
            content = data.get("content")
            if isinstance(content, str) and content.strip():
                lines.append(f"### {title}\n{content.strip()}")
        return "\n\n".join(lines) or None

    def _smartsheet_text(self, client: WeComGatewayClient, docid: str) -> str | None:
        try:
            meta = client.call("/smartsheet/get", {"docid": docid})
        except ChinaConnectorError:
            logger.warning("WeCom smartsheet %s unreadable", docid, exc_info=True)
            return None
        lines: list[str] = []
        for sheet in (meta.get("sheets") or [])[:_MAX_SHEETS_PER_DOC]:
            if not isinstance(sheet, dict):
                continue
            sheet_id = str(sheet.get("sheet_id") or "")
            title = str(sheet.get("title") or sheet_id)
            if not sheet_id:
                continue
            try:
                records = client.call(
                    "/smartsheet/records/list",
                    {
                        "docid": docid,
                        "sheet_id": sheet_id,
                        "limit": _MAX_SMARTSHEET_ROWS,
                    },
                )
            except ChinaConnectorError:
                logger.warning(
                    "WeCom smartsheet %s/%s records read failed", docid, sheet_id
                )
                continue
            rows = records.get("records") or []
            if not rows:
                continue
            lines.append(f"### {title} ({len(rows)} rows)")
            for row in rows:
                if not isinstance(row, dict):
                    continue
                cells = row.get("cells") or row.get("fields") or row
                lines.append(json.dumps(cells, ensure_ascii=False, default=str))
        return "\n".join(lines) or None

    def _smartpage_text(self, client: WeComGatewayClient, docid: str) -> str | None:
        try:
            result = client.call("/smartpage/pages/get", {"docid": docid})
        except ChinaConnectorError:
            logger.warning("WeCom smartpage %s unreadable", docid, exc_info=True)
            return None
        parts: list[str] = []
        for page in result.get("pages") or []:
            if not isinstance(page, dict):
                continue
            title = str(page.get("title") or "")
            body = page.get("content") or page.get("text") or ""
            if isinstance(body, str) and body.strip():
                parts.append(f"### {title}\n{body.strip()}" if title else body.strip())
        return "\n\n".join(parts) or None

    def _document_text(
        self, client: WeComGatewayClient, docid: str, doc_type: str
    ) -> str | None:
        if doc_type == "sheet":
            return self._sheet_text(client, docid)
        if doc_type == "smartsheet":
            return self._smartsheet_text(client, docid)
        if doc_type == "smartpage":
            return self._smartpage_text(client, docid)
        return self._doc_text(client, docid)

    # ── documents ────────────────────────────────────────────────────────

    def _load_documents(
        self, start: float | None = None, end: float | None = None
    ) -> GenerateDocumentsOutput:
        client = self._client_or_raise()
        doc_batch: list[Document | HierarchyNode] = []
        for info in self._discover_docs(client):
            docid = str(info.get("docid") or "")
            if not docid:
                continue
            doc_type = str(info.get("doc_type") or "doc")
            if doc_type not in _DOC_TYPES:
                doc_type = "doc"
            modified = _parse_cst(info.get("modify_time"))
            if modified is not None and start is not None and modified < start:
                continue
            text = self._document_text(client, docid, doc_type)
            title = str(info.get("doc_name") or docid)
            if not text:
                # Search snippets keep metadata-only docs findable.
                snippet = " ".join(
                    str(frag)
                    for frag in (info.get("sub_title_highlight") or [])
                    if isinstance(frag, str)
                ).strip()
                if not snippet:
                    continue
                text = snippet
            doc_batch.append(
                Document(
                    id=f"wecom-docs-{docid}",
                    source=DocumentSource.WECOM_DOCS,
                    semantic_identifier=title,
                    title=title,
                    sections=[TextSection(text=text)],
                    metadata={
                        "docid": docid,
                        "doc_type": doc_type,
                        "creator": str(info.get("creator_name") or ""),
                    },
                    doc_updated_at=modified,
                )
            )
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
