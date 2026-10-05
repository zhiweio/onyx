"""WeCom (企业微信) IM connector: indexes group-chat history via the
smart-robot CLI gateway.

Only conversations where the robot has messages are visible to the gateway,
and message history is capped at the trailing 7 days (platform rule).
Messages are grouped into one document per chat per day (CST day boundary),
which makes document ids derivable from the window's date math. The gateway
exposes no chat-member API, so these documents carry no external ACL —
visibility is governed by the connector-credential pair's access_type.

Credentials: ``wecom_bot_id`` / ``wecom_bot_secret`` (智能机器人 Bot ID/Secret).
"""

from __future__ import annotations

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
# Platform cap: chat history is only readable for the trailing 7 days.
_MAX_HISTORY_DAYS = 7
_DEFAULT_HISTORY_DAYS = 7
_MSG_PLACEHOLDER_TYPES = ("image", "file", "voice", "video", "mixed")


def _format_window(dt: datetime) -> str:
    return dt.astimezone(_CST).strftime("%Y-%m-%d %H:%M:%S")


def _message_text(message: dict[str, Any]) -> str | None:
    """Human-readable text of one ChatMessage; attachment-only messages
    become a short placeholder so the surrounding conversation still reads."""
    msg_type = str(message.get("msg_type") or "")
    if msg_type == "text":
        body = message.get("text")
        text = (
            str((body or {}).get("content") or "").strip()
            if isinstance(body, dict)
            else ""
        )
        return text or None
    if msg_type == "mixed":
        items = (message.get("mixed") or {}).get("items") or []
        parts = [
            str(item.get("text") or "")
            for item in items
            if isinstance(item, dict) and item.get("text")
        ]
        joined = " ".join(part.strip() for part in parts).strip()
        return joined or None
    if msg_type in _MSG_PLACEHOLDER_TYPES:
        return f"[{msg_type}]"
    return None


class WeComImConnector(LoadConnector, PollConnector):
    def __init__(
        self,
        batch_size: int = INDEX_BATCH_SIZE,
        history_days: int = _DEFAULT_HISTORY_DAYS,
        chat_ids: list[str] | None = None,
    ) -> None:
        self.batch_size = batch_size
        self.history_days = min(max(1, int(history_days)), _MAX_HISTORY_DAYS)
        self.chat_ids = [c for c in (chat_ids or []) if c]
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
        chat list means the robot has no gateway conversations yet."""
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
                f"Unexpected error while validating WeCom IM settings: {e}"
            ) from e

    def _target_chats(
        self, client: WeComGatewayClient, begin: datetime, end: datetime
    ) -> list[dict[str, Any]]:
        chats: dict[str, dict[str, Any]] = {}
        for page in client.iter_pages(
            "/chat/groups/list",
            {"begin_time": _format_window(begin), "end_time": _format_window(end)},
        ):
            for chat in page.get("chats") or []:
                if not isinstance(chat, dict):
                    continue
                chat_id = str(chat.get("chat_id") or "")
                if chat_id:
                    chats.setdefault(chat_id, chat)
        if self.chat_ids:
            wanted = set(self.chat_ids)
            return [c for cid, c in chats.items() if cid in wanted]
        return list(chats.values())

    @staticmethod
    def _day_key(ts: float) -> str:
        return datetime.fromtimestamp(ts, tz=_CST).strftime("%Y%m%d")

    @staticmethod
    def _day_label(day_key: str) -> str:
        return f"{day_key[:4]}-{day_key[4:6]}-{day_key[6:8]}"

    def _chat_messages(
        self,
        client: WeComGatewayClient,
        chat_id: str,
        begin: datetime,
        end: datetime,
    ) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        for page in client.iter_pages(
            "/chat/messages/list",
            {
                "chat_id": chat_id,
                "begin_time": _format_window(begin),
                "end_time": _format_window(end),
            },
        ):
            messages.extend(
                m for m in (page.get("messages") or []) if isinstance(m, dict)
            )
        return messages

    def _chat_day_documents(
        self,
        chat: dict[str, Any],
        messages: list[dict[str, Any]],
    ) -> list[Document]:
        chat_id = str(chat.get("chat_id"))
        chat_name = str(chat.get("chat_name") or chat_id)
        grouped: dict[str, tuple[float, list[str]]] = {}
        for message in messages:
            text = _message_text(message)
            if not text:
                continue
            send_time = message.get("send_time")
            if send_time is None:
                continue
            try:
                ts = float(str(send_time))
            except ValueError:
                continue
            # Seconds vs milliseconds: the gateway returns epoch seconds, but
            # stay defensive about ms-shaped values.
            if ts > 10**12:
                ts /= 1000.0
            sender = str(message.get("user_name") or message.get("userid") or "unknown")
            day_key = self._day_key(ts)
            last_ts, lines = grouped.get(day_key, (0.0, []))
            lines.append(f"{sender}: {text}")
            grouped[day_key] = (max(last_ts, ts), lines)
        documents: list[Document] = []
        for day_key, (last_ts, lines) in sorted(grouped.items()):
            day_label = self._day_label(day_key)
            documents.append(
                Document(
                    id=f"wecom-im-{chat_id}-{day_key}",
                    source=DocumentSource.WECOM_IM,
                    semantic_identifier=f"{chat_name} {day_label}",
                    title=chat_name,
                    sections=[TextSection(text="\n".join(lines))],
                    metadata={
                        "chat_id": chat_id,
                        "chat_name": chat_name,
                        "date": day_label,
                    },
                    doc_updated_at=last_ts or None,
                )
            )
        return documents

    def _load_documents(
        self, start: float | None = None, end: float | None = None
    ) -> GenerateDocumentsOutput:
        client = self._client_or_raise()
        now = datetime.now(tz=_CST)
        window_end = datetime.fromtimestamp(end, tz=_CST) if end is not None else now
        window_start = (
            datetime.fromtimestamp(start, tz=_CST)
            if start is not None
            else window_end - timedelta(days=self.history_days)
        )
        floor = now - timedelta(days=_MAX_HISTORY_DAYS)
        if window_start < floor:
            window_start = floor
        doc_batch: list[Document | HierarchyNode] = []
        for chat in self._target_chats(client, window_start, window_end):
            chat_id = str(chat.get("chat_id"))
            try:
                messages = self._chat_messages(
                    client, chat_id, window_start, window_end
                )
            except ChinaConnectorError:
                logger.warning(
                    "WeCom chat %s unreadable; skipping", chat_id, exc_info=True
                )
                continue
            for document in self._chat_day_documents(chat, messages):
                doc_batch.append(document)
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
