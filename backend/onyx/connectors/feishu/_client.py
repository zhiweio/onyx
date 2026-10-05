"""Shared Feishu OpenAPI client.

One client backs the whole Feishu connector family (wiki, drive, IM,
tasks): it owns the tenant-token lifecycle, open_id → email resolution,
and the permission-member → ExternalAccess mapping that every perm-sync
connector reuses.
"""

from __future__ import annotations

import re
import time
from typing import Any

import requests

from onyx.access.models import ExternalAccess
from onyx.connectors.china_common import (
    AppTokenManager,
    ChinaConnectorError,
    get_json,
    paginated,
    post_json,
)
from onyx.utils.logger import setup_logger

logger = setup_logger()

FEISHU_BASE = "https://open.feishu.cn/open-apis"
_TAG_RE = re.compile(r"<[^>]+>")

# Export-task job status: 0 success, 1 pending, 2 processing, 3 failed.
_EXPORT_DONE = 0
_EXPORT_RUNNING = (1, 2)
_EXPORT_POLL_ATTEMPTS = 30


def strip_html(text: str) -> str:
    return _TAG_RE.sub("", text)


class FeishuClient:
    """Tenant-token-authenticated Feishu OpenAPI client."""

    def __init__(self, app_id: str, app_secret: str) -> None:
        self._app_id = app_id
        self._app_secret = app_secret
        self._token = AppTokenManager(self._fetch_tenant_token)
        self._session: requests.Session | None = None
        # open_id → email, cached across a walk (contact lookups are the
        # slow path; one workspace walk should resolve each user once).
        self._email_cache: dict[str, str | None] = {}

    # ── auth ────────────────────────────────────────────────────────────

    def _fetch_tenant_token(self) -> tuple[str, int]:
        data = post_json(
            requests.Session(),
            f"{FEISHU_BASE}/auth/v3/tenant_access_token/internal",
            json_body={"app_id": self._app_id, "app_secret": self._app_secret},
        )
        if data.get("code") not in (0, None):
            raise ChinaConnectorError(f"Feishu token error: {data.get('msg')}")
        return str(data["tenant_access_token"]), int(data.get("expire", 7200))

    def session(self) -> requests.Session:
        """One pooled session whose Authorization header always carries the
        current tenant token."""
        if self._session is None:
            self._session = requests.Session()
        self._session.headers.update({"Authorization": f"Bearer {self._token.get()}"})
        return self._session

    # ── wiki ────────────────────────────────────────────────────────────

    def wiki_spaces(self) -> list[dict[str, Any]]:
        def page(page_token: str | None) -> tuple[list[dict[str, Any]], str | None]:
            params: dict[str, Any] = {"page_size": 50}
            if page_token:
                params["page_token"] = page_token
            data = get_json(
                self.session(), f"{FEISHU_BASE}/wiki/v2/spaces", params=params
            )
            if data.get("code") not in (0, None):
                raise ChinaConnectorError(f"Feishu spaces error: {data.get('msg')}")
            spaces = data.get("data") or {}
            # Feishu keeps returning a page_token on the last page; only
            # has_more=false marks the end.
            return list(spaces.get("items") or []), (
                spaces.get("page_token") if spaces.get("has_more") else None
            )

        return list(paginated(page))

    def wiki_nodes(self, space_id: str) -> list[dict[str, Any]]:
        def page(page_token: str | None) -> tuple[list[dict[str, Any]], str | None]:
            params: dict[str, Any] = {"page_size": 50}
            if page_token:
                params["page_token"] = page_token
            data = get_json(
                self.session(),
                f"{FEISHU_BASE}/wiki/v2/spaces/{space_id}/nodes",
                params=params,
            )
            if data.get("code") not in (0, None):
                raise ChinaConnectorError(f"Feishu nodes error: {data.get('msg')}")
            payload = data.get("data") or {}
            return list(payload.get("items") or []), (
                payload.get("page_token") if payload.get("has_more") else None
            )

        return list(paginated(page))

    def docx_raw_content(self, document_id: str) -> str | None:
        data = get_json(
            self.session(), f"{FEISHU_BASE}/docx/v1/documents/{document_id}/raw_content"
        )
        if data.get("code") not in (0, None):
            logger.warning("Feishu raw_content %s: %s", document_id, data.get("msg"))
            return None
        content = (data.get("data") or {}).get("content")
        return str(content) if content else None

    # ── permissions + contacts (shared perm-sync plumbing) ──────────────

    def permission_members(
        self, token: str, perm_type: str = "wiki"
    ) -> list[dict[str, Any]]:
        """Member list of one permissioned object (wiki node, drive file...)."""

        def page(page_token: str | None) -> tuple[list[dict[str, Any]], str | None]:
            params: dict[str, Any] = {"type": perm_type, "page_size": 50}
            if page_token:
                params["page_token"] = page_token
            data = get_json(
                self.session(),
                f"{FEISHU_BASE}/drive/v1/permissions/{token}/members",
                params=params,
            )
            if data.get("code") not in (0, None):
                raise ChinaConnectorError(f"Feishu members error: {data.get('msg')}")
            payload = data.get("data") or {}
            return list(payload.get("members") or []), (
                payload.get("page_token") if payload.get("has_more") else None
            )

        return list(paginated(page))

    def user_email(self, open_id: str) -> str | None:
        """Resolve one open_id to a work email via the single-user contact
        API (the batch_get path mis-routes to /users/{id} on this API)."""
        if open_id in self._email_cache:
            return self._email_cache[open_id]
        email: str | None = None
        try:
            data = get_json(
                self.session(),
                f"{FEISHU_BASE}/contact/v3/users/{open_id}",
                params={"user_id_type": "open_id"},
            )
            if data.get("code") in (0, None):
                user = (data.get("data") or {}).get("user") or {}
                if user.get("email"):
                    email = str(user["email"])
        except Exception:
            logger.debug("Feishu email lookup failed for %s", open_id)
        self._email_cache[open_id] = email
        return email

    def members_to_external_access(
        self, members: list[dict[str, Any]]
    ) -> ExternalAccess:
        emails: set[str] = set()
        group_ids: set[str] = set()
        for member in members:
            member_type = str(member.get("member_type") or "")
            member_id = str(member.get("member_id") or "")
            if not member_id:
                continue
            if member_type == "user":
                email = self.user_email(member_id)
                if email:
                    emails.add(email)
            elif member_type in ("group", "chat", "department"):
                group_ids.add(f"feishu:{member_id}")
        return ExternalAccess(
            external_user_emails=emails,
            external_user_group_ids=group_ids,
            is_public=False,
        )

    def token_external_access(
        self, token: str, perm_type: str = "wiki"
    ) -> ExternalAccess:
        """ExternalAccess for one permissioned object.

        An object whose members cannot be listed (app scope missing,
        restricted container) yields the empty/private fallback —
        restrictive beats unknown."""
        try:
            return self.members_to_external_access(
                self.permission_members(token, perm_type)
            )
        except Exception:
            logger.warning(
                "Feishu permission members unreadable for %s; using private ACL",
                token,
                exc_info=True,
            )
            return ExternalAccess.empty()

    # ── drive ───────────────────────────────────────────────────────────

    def drive_root_folder_token(self) -> str:
        data = get_json(
            self.session(), f"{FEISHU_BASE}/drive/explorer/v2/root_folder/meta"
        )
        if data.get("code") not in (0, None):
            raise ChinaConnectorError(f"Feishu root folder error: {data.get('msg')}")
        payload = data.get("data") or {}
        # the v2 meta endpoint answers with `token`; older shapes used
        # `root_folder_token` — accept both
        return str(payload.get("token") or payload.get("root_folder_token") or "")

    def drive_folder_files(self, folder_token: str) -> list[dict[str, Any]]:
        def page(page_token: str | None) -> tuple[list[dict[str, Any]], str | None]:
            params: dict[str, Any] = {"folder_token": folder_token, "page_size": 50}
            if page_token:
                params["page_token"] = page_token
            data = get_json(
                self.session(), f"{FEISHU_BASE}/drive/v1/files", params=params
            )
            if data.get("code") not in (0, None):
                raise ChinaConnectorError(f"Feishu drive list error: {data.get('msg')}")
            payload = data.get("data") or {}
            return list(payload.get("files") or []), (
                payload.get("page_token") if payload.get("has_more") else None
            )

        return list(paginated(page))

    def drive_media_download(self, file_token: str) -> bytes | None:
        try:
            resp = self.session().get(
                f"{FEISHU_BASE}/drive/v1/medias/{file_token}/download", timeout=120
            )
        except Exception:
            logger.exception("Feishu media download failed: %s", file_token)
            return None
        if resp.status_code != 200:
            logger.warning(
                "Feishu media download %s -> %s", file_token, resp.status_code
            )
            return None
        return resp.content

    def drive_export_bytes(
        self, token: str, doc_type: str, export_ext: str
    ) -> bytes | None:
        """Export an online document (sheet/bitable/...) to a file format
        and download the result. Returns None on any failure."""
        session = self.session()
        try:
            created = post_json(
                session,
                f"{FEISHU_BASE}/drive/v1/export_tasks",
                json_body={
                    "file_extension": export_ext,
                    "token": token,
                    "type": doc_type,
                },
            )
            if created.get("code") not in (0, None):
                logger.warning(
                    "Feishu export task create %s: %s", token, created.get("msg")
                )
                return None
            ticket = (created.get("data") or {}).get("ticket")
            if not ticket:
                return None
            for _ in range(_EXPORT_POLL_ATTEMPTS):
                poll = get_json(
                    session,
                    f"{FEISHU_BASE}/drive/v1/export_tasks/{ticket}",
                    params={"token": token, "type": doc_type},
                )
                result = (poll.get("data") or {}).get("result") or {}
                status = int(result.get("job_status") or 0)
                if status == _EXPORT_DONE and result.get("file_token"):
                    download = session.get(
                        f"{FEISHU_BASE}/drive/v1/export_tasks/file/"
                        f"{result['file_token']}/download",
                        timeout=120,
                    )
                    return download.content if download.status_code == 200 else None
                if status not in _EXPORT_RUNNING:
                    logger.warning("Feishu export task %s failed: %s", token, poll)
                    return None
                time.sleep(1)
            logger.warning("Feishu export task %s timed out", token)
        except Exception:
            logger.exception("Feishu export failed: %s", token)
        return None

    # ── IM ──────────────────────────────────────────────────────────────

    def im_chats(self) -> list[dict[str, Any]]:
        """Group chats the app's bot belongs to."""

        def page(page_token: str | None) -> tuple[list[dict[str, Any]], str | None]:
            params: dict[str, Any] = {"page_size": 100}
            if page_token:
                params["page_token"] = page_token
            data = get_json(self.session(), f"{FEISHU_BASE}/im/v1/chats", params=params)
            if data.get("code") not in (0, None):
                raise ChinaConnectorError(f"Feishu chats error: {data.get('msg')}")
            payload = data.get("data") or {}
            return list(payload.get("items") or []), (
                payload.get("page_token") if payload.get("has_more") else None
            )

        return list(paginated(page))

    def im_messages(
        self,
        chat_id: str,
        start: float | None = None,
        end: float | None = None,
    ) -> list[dict[str, Any]]:
        """Chat history in [start, end) (unix seconds), oldest first."""

        def page(page_token: str | None) -> tuple[list[dict[str, Any]], str | None]:
            params: dict[str, Any] = {
                "container_id_type": "chat",
                "container_id": chat_id,
                "sort_type": "ByCreateTimeAsc",
                "page_size": 50,
            }
            if start is not None:
                params["start_time"] = str(int(start))
            if end is not None:
                params["end_time"] = str(int(end))
            if page_token:
                params["page_token"] = page_token
            data = get_json(
                self.session(), f"{FEISHU_BASE}/im/v1/messages", params=params
            )
            if data.get("code") not in (0, None):
                raise ChinaConnectorError(f"Feishu messages error: {data.get('msg')}")
            payload = data.get("data") or {}
            return list(payload.get("items") or []), (
                payload.get("page_token") if payload.get("has_more") else None
            )

        return list(paginated(page))

    def im_chat_members(self, chat_id: str) -> list[dict[str, Any]]:
        def page(page_token: str | None) -> tuple[list[dict[str, Any]], str | None]:
            params: dict[str, Any] = {"member_id_type": "open_id", "page_size": 100}
            if page_token:
                params["page_token"] = page_token
            data = get_json(
                self.session(),
                f"{FEISHU_BASE}/im/v1/chats/{chat_id}/members",
                params=params,
            )
            if data.get("code") not in (0, None):
                raise ChinaConnectorError(
                    f"Feishu chat members error: {data.get('msg')}"
                )
            payload = data.get("data") or {}
            return list(payload.get("items") or []), (
                payload.get("page_token") if payload.get("has_more") else None
            )

        return list(paginated(page))

    # ── tasks (v2) ──────────────────────────────────────────────────────

    def task_tasklists(self) -> list[dict[str, Any]]:
        def page(page_token: str | None) -> tuple[list[dict[str, Any]], str | None]:
            params: dict[str, Any] = {"page_size": 100}
            if page_token:
                params["page_token"] = page_token
            data = get_json(
                self.session(), f"{FEISHU_BASE}/task/v2/tasklists", params=params
            )
            if data.get("code") not in (0, None):
                raise ChinaConnectorError(f"Feishu tasklists error: {data.get('msg')}")
            payload = data.get("data") or {}
            return list(payload.get("items") or []), (
                payload.get("page_token") if payload.get("has_more") else None
            )

        return list(paginated(page))

    def tasklist_tasks(self, tasklist_guid: str) -> list[dict[str, Any]]:
        def page(page_token: str | None) -> tuple[list[dict[str, Any]], str | None]:
            params: dict[str, Any] = {"page_size": 100}
            if page_token:
                params["page_token"] = page_token
            data = get_json(
                self.session(),
                f"{FEISHU_BASE}/task/v2/tasklists/{tasklist_guid}/tasks",
                params=params,
            )
            if data.get("code") not in (0, None):
                raise ChinaConnectorError(f"Feishu tasks error: {data.get('msg')}")
            payload = data.get("data") or {}
            return list(payload.get("items") or []), (
                payload.get("page_token") if payload.get("has_more") else None
            )

        return list(paginated(page))

    def task_detail(self, task_guid: str) -> dict[str, Any] | None:
        data = get_json(self.session(), f"{FEISHU_BASE}/task/v2/tasks/{task_guid}")
        if data.get("code") not in (0, None):
            logger.warning("Feishu task %s: %s", task_guid, data.get("msg"))
            return None
        task = (data.get("data") or {}).get("task")
        return dict(task) if task else None
