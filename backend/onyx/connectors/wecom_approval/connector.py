"""WeCom (企业微信) approval connector: indexes OA 审批单 as work tickets.

One document per approval request. The approval APIs expose no per-document
viewer list, so these documents carry no external ACL — visibility is
governed by the connector-credential pair's access_type.

Credentials: ``wecom_corp_id`` / ``wecom_corp_secret``. The app needs the
OA approval data permission.

NOTE: response field names are handled defensively; live verification
against a real tenant is still pending.
"""

from __future__ import annotations

import time
from typing import Any

from onyx.configs.app_configs import INDEX_BATCH_SIZE
from onyx.configs.constants import DocumentSource
from onyx.connectors.china_common import clean_identifier
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
from onyx.connectors.wecom._client import WeComClient
from onyx.utils.logger import setup_logger

logger = setup_logger()

_SP_STATUS = {
    1: "审批中",
    2: "已通过",
    3: "已驳回",
    4: "已撤销",
    6: "通过后撤销",
    7: "已删除",
    10: "已支付",
}
_DEFAULT_HISTORY_DAYS = 90
# getapprovalinfo caps starttime~endtime at roughly a month per call.
_WINDOW_SECONDS = 30 * 86400


def _apply_data_texts(info: dict[str, Any]) -> list[str]:
    """Flatten the apply_data form controls into readable lines."""
    lines: list[str] = []
    apply_data = info.get("apply_data") or {}
    for control in apply_data.get("controls") or []:
        if not isinstance(control, dict):
            continue
        label = str(control.get("title") or control.get("control") or "")
        value = control.get("value") or {}
        texts: list[str] = []
        if value.get("text"):
            texts.append(str(value["text"]))
        for entry in value.get("new_value") or []:
            if isinstance(entry, dict):
                text = entry.get("text") or entry.get("value")
                if text:
                    texts.append(str(text))
            elif entry:
                texts.append(str(entry))
        if texts:
            lines.append(f"{label}: {'、'.join(texts)}")
    return lines


def _applicant_id(info: dict[str, Any]) -> str:
    applyader = info.get("applyader") or {}
    return str(applyader.get("userid") or applyader.get("applyader_userid") or "")


class WeComApprovalConnector(LoadConnector, PollConnector):
    def __init__(
        self,
        batch_size: int = INDEX_BATCH_SIZE,
        history_days: int = _DEFAULT_HISTORY_DAYS,
        template_ids: list[str] | None = None,
    ) -> None:
        self.batch_size = batch_size
        self.history_days = max(1, int(history_days))
        self.template_ids = [t for t in (template_ids or []) if t]
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

    def _approval_ids(self, client: WeComClient, start: float, end: float) -> list[str]:
        sp_nos: list[str] = []
        window_start = start
        while window_start < end:
            window_end = min(window_start + _WINDOW_SECONDS, end)
            cursor = 0
            while True:
                data = client.post(
                    "/oa/getapprovalinfo",
                    {
                        "starttime": int(window_start),
                        "endtime": int(window_end),
                        "cursor": cursor,
                        "size": 100,
                    },
                )
                sp_nos.extend(str(sp_no) for sp_no in data.get("sp_no_list") or [])
                next_cursor = data.get("next_cursor")
                if not next_cursor or int(next_cursor) <= cursor:
                    break
                cursor = int(next_cursor)
            window_start = window_end
        return sp_nos

    def _approval_document(self, client: WeComClient, sp_no: str) -> Document | None:
        try:
            detail = client.post("/oa/getapprovaldetail", {"sp_no": sp_no})
        except Exception:
            logger.warning(
                "WeCom approval %s unreadable; skipping", sp_no, exc_info=True
            )
            return None
        info = detail.get("info") or {}
        if self.template_ids and str(info.get("template_id")) not in self.template_ids:
            return None
        sp_name = str(info.get("sp_name") or "审批")
        status = _SP_STATUS.get(int(info.get("sp_status") or 0), "未知")
        applicant = _applicant_id(info) or "unknown"
        apply_time = float(info.get("apply_time") or 0)
        title = f"{sp_name}（{applicant}）"
        lines = [
            f"类型: {sp_name}",
            f"申请人: {applicant}",
            f"状态: {status}",
            f"申请时间: {apply_time}",
        ]
        lines.extend(_apply_data_texts(info))
        text = "\n".join(lines)
        return Document(
            id=f"wecom-approval-{sp_no}",
            source=DocumentSource.WECOM_APPROVAL,
            semantic_identifier=title,
            title=clean_identifier(title, sp_no),
            sections=[TextSection(text=text)],
            metadata={
                "template_id": str(info.get("template_id") or ""),
                "status": status,
            },
            doc_updated_at=apply_time or None,
        )

    def _load(
        self, start: float | None = None, end: float | None = None
    ) -> GenerateDocumentsOutput:
        client = self._client_or_raise()
        if end is None:
            end = time.time()
        if start is None:
            start = end - self.history_days * 86400
        # list is invariant: the batch must match the declared
        # `Iterator[list[Document | HierarchyNode]]` yield type.
        batch: list[Document | HierarchyNode] = []
        for sp_no in self._approval_ids(client, start, end):
            document = self._approval_document(client, sp_no)
            if document is None:
                continue
            batch.append(document)
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
