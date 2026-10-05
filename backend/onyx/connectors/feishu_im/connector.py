"""Feishu (Lark) IM connector: indexes group-chat history.

Only chats where the app's bot is a member can be read (Feishu rule).
Messages are grouped into one document per chat per day (day boundary in
CST), which makes document ids derivable without re-reading history —
permission sync replays the same date math instead of re-fetching
messages. Per-chat ACLs come from the chat member list (open_id → email
via contact lookup); chats whose members cannot be listed fall back to a
restrictive (empty, private) ACL.

Credentials: ``feishu_app_id`` / ``feishu_app_secret``. The app needs IM
history-read scopes plus ``im:chat:readonly``.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from onyx.access.models import ExternalAccess
from onyx.configs.app_configs import INDEX_BATCH_SIZE
from onyx.configs.constants import DocumentSource
from onyx.connectors.china_common import ChinaConnectorError
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

_CST = timezone(timedelta(hours=8))
_DEFAULT_HISTORY_DAYS = 90
_MSG_PLACEHOLDER_TYPES = ("image", "file", "audio", "media", "sticker")


def _message_text(message: dict[str, Any]) -> str | None:
    """Human-readable text of one im/v1 message; attachment-only messages
    become a short placeholder so the surrounding conversation still reads."""
    try:
        body = json.loads(str((message.get("body") or {}).get("content") or "{}"))
    except (TypeError, ValueError):
        return None
    msg_type = str(message.get("msg_type") or "")
    if msg_type == "text":
        text = str(body.get("text") or "").strip()
        return text or None
    if msg_type == "post":
        parts: list[str] = []
        title = body.get("title")
        if title:
            parts.append(str(title))
        content = body.get("content")
        if isinstance(content, list):
            for paragraph in content:
                if not isinstance(paragraph, list):
                    continue
                line = "".join(
                    str(element.get("text") or element.get("href") or "")
                    for element in paragraph
                    if isinstance(element, dict)
                ).strip()
                if line:
                    parts.append(line)
        return "\n".join(parts) or None
    if msg_type in _MSG_PLACEHOLDER_TYPES:
        return f"[{msg_type}]"
    return None


class FeishuImConnector(SlimConnectorWithPermSync, LoadConnector, PollConnector):
    def __init__(
        self,
        batch_size: int = INDEX_BATCH_SIZE,
        history_days: int = _DEFAULT_HISTORY_DAYS,
        chat_ids: list[str] | None = None,
    ) -> None:
        self.batch_size = batch_size
        self.history_days = max(1, int(history_days))
        self.chat_ids = [c for c in (chat_ids or []) if c]
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
        """Bad app credentials and missing IM scopes are the two
        misconfigurations a test call can detect."""
        client = self._client_or_raise()
        try:
            client.session()
        except ChinaConnectorError as e:
            raise CredentialInvalidError(f"Invalid Feishu app credentials: {e}") from e
        except Exception as e:
            raise UnexpectedValidationError(
                f"Unexpected error while validating Feishu IM settings: {e}"
            ) from e
        try:
            client.im_chats()
        except ChinaConnectorError as e:
            raise InsufficientPermissionsError(
                "Feishu rejected the chat list; confirm the app has the IM "
                "chat-read scope and the bot is inside the target chats: "
                f"{e}"
            ) from e
        except Exception as e:
            raise UnexpectedValidationError(
                f"Unexpected error while validating Feishu IM settings: {e}"
            ) from e

    def _target_chats(self, client: FeishuClient) -> list[dict[str, Any]]:
        chats = client.im_chats()
        if not self.chat_ids:
            return chats
        wanted = set(self.chat_ids)
        return [chat for chat in chats if str(chat.get("chat_id")) in wanted]

    @staticmethod
    def _day_key(ts: float) -> str:
        return datetime.fromtimestamp(ts, tz=_CST).strftime("%Y%m%d")

    @staticmethod
    def _day_label(day_key: str) -> str:
        return f"{day_key[:4]}-{day_key[4:6]}-{day_key[6:8]}"

    def _group_messages_by_day(
        self, messages: list[dict[str, Any]]
    ) -> dict[str, list[tuple[float, dict[str, Any]]]]:
        grouped: dict[str, list[tuple[float, dict[str, Any]]]] = {}
        for message in messages:
            create_time = message.get("create_time")
            if create_time in (None, ""):
                continue
            # im/v1 returns create_time as a millisecond string.
            ts = float(create_time) / 1000.0
            grouped.setdefault(self._day_key(ts), []).append((ts, message))
        return grouped

    def _sender_label(self, client: FeishuClient, message: dict[str, Any]) -> str:
        sender = message.get("sender") or {}
        sender_id = str(sender.get("id") or "")
        if not sender_id:
            return "unknown"
        email = client.user_email(sender_id)
        if email:
            return email
        return f"user-{sender_id[-6:]}"

    def _chat_day_document(
        self,
        client: FeishuClient,
        chat: dict[str, Any],
        day_key: str,
        entries: list[tuple[float, dict[str, Any]]],
    ) -> Document:
        chat_id = str(chat.get("chat_id"))
        chat_name = str(chat.get("name") or chat_id)
        day_label = self._day_label(day_key)
        sections: list[TextSection] = []
        last_ts = 0.0
        for ts, message in entries:
            text = _message_text(message)
            if not text:
                continue
            sender = self._sender_label(client, message)
            sections.append(TextSection(text=f"{sender}: {text}"))
            last_ts = max(last_ts, ts)
        title = f"{chat_name} {day_label}"
        return Document(
            id=f"feishu-im-{chat_id}-{day_key}",
            source=DocumentSource.FEISHU_IM,
            semantic_identifier=title,
            title=chat_name,
            sections=sections,
            metadata={"chat_id": chat_id, "chat_name": chat_name, "date": day_label},
            doc_updated_at=last_ts or None,
        )

    def _chat_documents(
        self,
        client: FeishuClient,
        chat: dict[str, Any],
        start: float | None,
        end: float | None,
    ) -> list[Document]:
        chat_id = str(chat.get("chat_id"))
        try:
            messages = client.im_messages(chat_id, start=start, end=end)
        except ChinaConnectorError:
            # Bot removed from the chat, or the chat was deleted: skip it,
            # permission sync will stop listing the corresponding docs.
            logger.warning(
                "Feishu chat %s unreadable; skipping", chat_id, exc_info=True
            )
            return []
        grouped = self._group_messages_by_day(messages)
        return [
            self._chat_day_document(client, chat, day_key, entries)
            for day_key, entries in sorted(grouped.items())
        ]

    def _load_documents(
        self, start: float | None = None, end: float | None = None
    ) -> GenerateDocumentsOutput:
        client = self._client_or_raise()
        if end is None:
            end = datetime.now(tz=_CST).timestamp()
        if start is None:
            start = end - self.history_days * 86400
        # list is invariant: the batch must match the declared
        # `Iterator[list[Document | HierarchyNode]]` yield type.
        doc_batch: list[Document | HierarchyNode] = []
        for chat in self._target_chats(client):
            for document in self._chat_documents(client, chat, start, end):
                if not document.sections:
                    continue
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

    # ── permission sync ──────────────────────────────────────────────────

    def _chat_external_access(
        self, client: FeishuClient, chat_id: str
    ) -> ExternalAccess:
        """Chat member list → ExternalAccess; unreadable chats yield the
        restrictive empty/private fallback."""
        try:
            members = client.im_chat_members(chat_id)
        except Exception:
            logger.warning(
                "Feishu chat members unreadable for %s; using private ACL",
                chat_id,
                exc_info=True,
            )
            return ExternalAccess.empty()
        emails: set[str] = set()
        for member in members:
            member_id = str(member.get("member_id") or "")
            if not member_id:
                continue
            email = client.user_email(member_id)
            if email:
                emails.add(email)
        return ExternalAccess(
            external_user_emails=emails, external_user_group_ids=set(), is_public=False
        )

    def retrieve_all_slim_docs_perm_sync(
        self,
        start: SecondsSinceUnixEpoch | None = None,
        end: SecondsSinceUnixEpoch | None = None,
        callback: Any = None,
    ) -> GenerateSlimDocumentOutput:
        """Emit one SlimDocument per (chat, day) in the configured history
        window. Document ids are pure date math — no message reads needed.

        Time filters are ignored on purpose: permission sync wants full
        coverage regardless of edit recency."""
        del start, end, callback
        client = self._client_or_raise()
        # list is invariant: the batch must match the declared
        # `Iterator[list[SlimDocument | HierarchyNode]]` yield type.
        batch: list[SlimDocument | HierarchyNode] = []
        today = datetime.now(tz=_CST).date()
        for chat in self._target_chats(client):
            chat_id = str(chat.get("chat_id"))
            access = self._chat_external_access(client, chat_id)
            for day_offset in range(self.history_days + 1):
                day = today - timedelta(days=day_offset)
                day_key = day.strftime("%Y%m%d")
                batch.append(
                    SlimDocument(
                        id=f"feishu-im-{chat_id}-{day_key}",
                        external_access=access,
                    )
                )
                if len(batch) >= self.batch_size:
                    yield batch
                    batch = []
        if batch:
            yield batch
