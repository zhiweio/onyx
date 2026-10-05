#!/usr/bin/env python3
"""Feishu Open API wrapper for the Onyx Craft sandbox.

Common Feishu operations exposed as subcommands; anything else goes through
`raw`. Output is JSON on stdout. No auth handling here — the egress proxy
injects the connected user's Feishu access token on the wire.

Feishu signals business failure with HTTP 200 + {"code": <nonzero>,
"msg": "..."}; those (and transport errors) surface as {"ok": false, ...}.
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Any

_BASE = "https://open.feishu.cn/open-apis"
_HTTP_TIMEOUT_SECONDS = 180
_PAGE_SIZE = 50
_DEFAULT_LIMIT = 100


def _prune(value: Any) -> Any:
    """Recursively drop None / "" / [] / {} so LLM-facing output stays
    small. Booleans and 0 are kept — they carry signal."""
    if isinstance(value, dict):
        out = {k: _prune(v) for k, v in value.items()}
        return {k: v for k, v in out.items() if v not in (None, "", [], {})}
    if isinstance(value, list):
        return [_prune(v) for v in value]
    return value


def _call(
    method: str,
    path: str,
    params: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """One Open API request; returns the parsed envelope's data payload."""
    url = _BASE + path
    query = {k: str(v) for k, v in (params or {}).items() if v is not None}
    if query:
        url += "?" + urllib.parse.urlencode(query)
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(  # noqa: S310 — fixed https base url
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    try:
        with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT_SECONDS) as resp:  # noqa: S310
            envelope = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:2000]
        return {"ok": False, "http_status": exc.code, "msg": detail}
    except urllib.error.URLError as exc:
        return {"ok": False, "msg": str(exc.reason)}
    code = envelope.get("code")
    if code not in (None, 0):
        return {
            "ok": False,
            "code": code,
            "msg": envelope.get("msg"),
            "data": envelope.get("data"),
        }
    return envelope.get("data") or {"ok": True}


def _paginate(
    method: str,
    path: str,
    params: dict[str, Any],
    items_key: str,
    limit: int,
    token_key: str = "page_token",
) -> dict[str, Any]:
    """Accumulate list results across cursor pages up to `limit`."""
    items: list[dict[str, Any]] = []
    query = dict(params)
    while len(items) < limit:
        query.setdefault("page_size", _PAGE_SIZE)
        data = _call(method, path, params=query)
        if isinstance(data, dict) and data.get("ok") is False:
            return data
        page = data.get(items_key) if isinstance(data, dict) else None
        if not page:
            break
        items.extend(page)
        nxt = data.get(token_key) or data.get("next_page_token")
        if not nxt or not data.get("has_more", True):
            break
        query[token_key] = nxt
        query.pop("next_page_token", None)
    return {"items": items[:limit]}


def _out(value: Any) -> None:
    print(json.dumps(_prune(value), ensure_ascii=False, indent=2))


def _content_arg(args: argparse.Namespace) -> str:
    if args.content:
        return args.content
    if args.text is None:
        raise SystemExit("provide --text or --content JSON")
    return json.dumps({"text": args.text}, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Command handlers — one per subcommand, dispatched by name in main().
# ---------------------------------------------------------------------------


def _cmd_chats(a: argparse.Namespace) -> dict[str, Any]:
    return _paginate("GET", "/im/v1/chats", {}, "items", a.limit)


def _cmd_history(a: argparse.Namespace) -> dict[str, Any]:
    return _paginate(
        "GET",
        "/im/v1/messages",
        {"chat_id": a.chat_id, "start_time": a.start, "end_time": a.end},
        "items",
        a.limit,
    )


def _cmd_read(a: argparse.Namespace) -> dict[str, Any]:
    return _call("GET", f"/im/v1/messages/{a.message_id}")


def _cmd_send(a: argparse.Namespace) -> dict[str, Any]:
    return _call(
        "POST",
        "/im/v1/messages",
        params={"receive_id_type": a.receive_id_type},
        body={
            "receive_id": a.receive_id,
            "msg_type": a.msg_type,
            "content": _content_arg(a),
        },
    )


def _cmd_reply(a: argparse.Namespace) -> dict[str, Any]:
    return _call(
        "POST",
        f"/im/v1/messages/{a.message_id}/reply",
        body={"msg_type": a.msg_type, "content": _content_arg(a)},
    )


def _cmd_search_docs(a: argparse.Namespace) -> dict[str, Any]:
    return _call(
        "POST",
        "/suite/docs-api/search/object",
        body={"search_key": a.query, "count": a.limit},
    )


def _cmd_search_messages(a: argparse.Namespace) -> dict[str, Any]:
    return _call(
        "POST",
        "/search/v2/message",
        body={"search_key": a.query, "page_size": a.limit},
    )


def _cmd_doc(a: argparse.Namespace) -> dict[str, Any]:
    return _call("GET", f"/docx/v1/documents/{a.document_id}/raw_content")


def _cmd_doc_blocks(a: argparse.Namespace) -> dict[str, Any]:
    return _paginate(
        "GET", f"/docx/v1/documents/{a.document_id}/blocks", {}, "items", a.limit
    )


def _cmd_doc_create(a: argparse.Namespace) -> dict[str, Any]:
    return _call(
        "POST",
        "/docx/v1/documents",
        body={"title": a.title, "folder_token": a.folder_token},
    )


def _cmd_wiki_spaces(a: argparse.Namespace) -> dict[str, Any]:
    return _paginate("GET", "/wiki/v2/spaces", {}, "items", a.limit)


def _cmd_wiki_nodes(a: argparse.Namespace) -> dict[str, Any]:
    return _paginate("GET", f"/wiki/v2/spaces/{a.space_id}/nodes", {}, "items", a.limit)


def _cmd_drive_files(a: argparse.Namespace) -> dict[str, Any]:
    params: dict[str, Any] = {"page_size": _PAGE_SIZE}
    if a.folder_token:
        params["folder_token"] = a.folder_token
    else:
        root = _call("GET", "/drive/explorer/v2/root_folder/meta")
        if isinstance(root, dict) and root.get("ok") is False:
            return root
        params["folder_token"] = root.get("token")
    return _paginate(
        "GET", "/drive/v1/files", params, "files", a.limit, token_key="next_page_token"
    )


def _cmd_download(a: argparse.Namespace) -> dict[str, Any]:
    url = f"{_BASE}/drive/v1/medias/{a.file_token}/download"
    req = urllib.request.Request(url)  # noqa: S310 — fixed https base url
    try:
        with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT_SECONDS) as resp:  # noqa: S310
            payload = resp.read()
    except urllib.error.HTTPError as exc:
        return {"ok": False, "http_status": exc.code}
    with open(a.out, "wb") as fh:
        fh.write(payload)
    return {"ok": True, "path": a.out}


def _cmd_sheet_values(a: argparse.Namespace) -> dict[str, Any]:
    encoded = urllib.parse.quote(a.range, safe="!:")
    return _call(
        "GET", f"/sheets/v2/spreadsheets/{a.spreadsheet_token}/values/{encoded}"
    )


def _cmd_sheet_write(a: argparse.Namespace) -> dict[str, Any]:
    return _call(
        "PUT",
        f"/sheets/v2/spreadsheets/{a.spreadsheet_token}/values",
        body={"valueRange": {"range": a.range, "values": json.loads(a.values)}},
    )


def _cmd_bitable_tables(a: argparse.Namespace) -> dict[str, Any]:
    return _paginate(
        "GET", f"/bitable/v1/apps/{a.app_token}/tables", {}, "items", _DEFAULT_LIMIT
    )


def _cmd_bitable_records(a: argparse.Namespace) -> dict[str, Any]:
    return _paginate(
        "GET",
        f"/bitable/v1/apps/{a.app_token}/tables/{a.table_id}/records",
        {},
        "items",
        a.limit,
    )


def _cmd_bitable_search(a: argparse.Namespace) -> dict[str, Any]:
    return _call(
        "POST",
        f"/bitable/v1/apps/{a.app_token}/tables/{a.table_id}/records/search",
        body=json.loads(a.body) if a.body else {},
    )


def _cmd_bitable_create_record(a: argparse.Namespace) -> dict[str, Any]:
    return _call(
        "POST",
        f"/bitable/v1/apps/{a.app_token}/tables/{a.table_id}/records",
        body={"fields": json.loads(a.fields)},
    )


def _cmd_tasklists(_a: argparse.Namespace) -> dict[str, Any]:
    return _paginate("GET", "/task/v2/tasklists", {}, "items", _DEFAULT_LIMIT)


def _cmd_tasks(a: argparse.Namespace) -> dict[str, Any]:
    return _paginate(
        "GET", f"/task/v2/tasklists/{a.tasklist_guid}/tasks", {}, "items", a.limit
    )


def _cmd_task_create(a: argparse.Namespace) -> dict[str, Any]:
    body: dict[str, Any] = {"summary": a.summary, "description": a.description}
    if a.due:
        body["due"] = {"date": a.due, "is_timestamp": "T" in a.due}
    return _call("POST", "/task/v2/tasks", body=body)


def _cmd_task_complete(a: argparse.Namespace) -> dict[str, Any]:
    return _call(
        "PATCH",
        f"/task/v2/tasks/{a.task_guid}",
        body={"completed_time": str(int(time.time()))},
    )


def _cmd_calendars(_a: argparse.Namespace) -> dict[str, Any]:
    return _paginate("GET", "/calendar/v4/calendars", {}, "items", _DEFAULT_LIMIT)


def _cmd_events(a: argparse.Namespace) -> dict[str, Any]:
    return _paginate(
        "GET",
        f"/calendar/v4/calendars/{a.calendar_id}/events",
        {"start_time": a.start, "end_time": a.end},
        "items",
        a.limit,
    )


def _cmd_event_create(a: argparse.Namespace) -> dict[str, Any]:
    body: dict[str, Any] = {
        "summary": a.summary,
        "start_time": {"timestamp": a.start},
        "end_time": {"timestamp": a.end},
        "description": a.description,
    }
    if a.attendee:
        body["attendees"] = [
            {"type": "user", "is_optional": False, "id": attendee}
            for attendee in a.attendee
        ]
    return _call("POST", f"/calendar/v4/calendars/{a.calendar_id}/events", body=body)


def _cmd_user(a: argparse.Namespace) -> dict[str, Any]:
    return _call(
        "GET",
        f"/contact/v3/users/{a.user_id}",
        params={"user_id_type": a.id_type},
    )


def _cmd_dept_users(a: argparse.Namespace) -> dict[str, Any]:
    return _paginate(
        "GET",
        "/contact/v3/users/find_by_department",
        {"department_id": a.department_id},
        "items",
        a.limit,
    )


def _cmd_resolve_users(a: argparse.Namespace) -> dict[str, Any]:
    return _call(
        "POST",
        "/contact/v3/users/batch_get_id",
        body={"emails": a.emails},
        params={"user_id_type": "open_id"},
    )


def _cmd_raw(a: argparse.Namespace) -> dict[str, Any]:
    params = dict(p.split("=", 1) for p in a.param)
    return _call(
        a.method, a.path, params=params, body=json.loads(a.data) if a.data else None
    )


_HANDLERS: dict[str, Callable[[argparse.Namespace], dict[str, Any]]] = {
    "chats": _cmd_chats,
    "history": _cmd_history,
    "read": _cmd_read,
    "send": _cmd_send,
    "reply": _cmd_reply,
    "search-docs": _cmd_search_docs,
    "search-messages": _cmd_search_messages,
    "doc": _cmd_doc,
    "doc-blocks": _cmd_doc_blocks,
    "doc-create": _cmd_doc_create,
    "wiki-spaces": _cmd_wiki_spaces,
    "wiki-nodes": _cmd_wiki_nodes,
    "drive-files": _cmd_drive_files,
    "download": _cmd_download,
    "sheet-values": _cmd_sheet_values,
    "sheet-write": _cmd_sheet_write,
    "bitable-tables": _cmd_bitable_tables,
    "bitable-records": _cmd_bitable_records,
    "bitable-search": _cmd_bitable_search,
    "bitable-create-record": _cmd_bitable_create_record,
    "tasklists": _cmd_tasklists,
    "tasks": _cmd_tasks,
    "task-create": _cmd_task_create,
    "task-complete": _cmd_task_complete,
    "calendars": _cmd_calendars,
    "events": _cmd_events,
    "event-create": _cmd_event_create,
    "user": _cmd_user,
    "dept-users": _cmd_dept_users,
    "resolve-users": _cmd_resolve_users,
    "raw": _cmd_raw,
}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("chats", help="List group chats")
    p.add_argument("--limit", type=int, default=_DEFAULT_LIMIT)

    p = sub.add_parser("history", help="List a chat's messages")
    p.add_argument("chat_id")
    p.add_argument("--start", help="Unix sec, inclusive")
    p.add_argument("--end", help="Unix sec, inclusive")
    p.add_argument("--limit", type=int, default=_DEFAULT_LIMIT)

    p = sub.add_parser("read", help="Read one message")
    p.add_argument("message_id")

    p = sub.add_parser("send", help="Send a message")
    p.add_argument("receive_id", help="open_id / chat_id / email value")
    p.add_argument(
        "--receive-id-type",
        default="chat_id",
        choices=["open_id", "union_id", "email", "chat_id"],
    )
    p.add_argument(
        "--msg-type",
        default="text",
        choices=["text", "post", "image", "interactive", "share_chat", "share_user"],
    )
    p.add_argument("--text", help="Plain text content (msg_type=text)")
    p.add_argument("--content", help="Full content JSON string")

    p = sub.add_parser("reply", help="Reply in a message thread")
    p.add_argument("message_id")
    p.add_argument("--msg-type", default="text")
    p.add_argument("--text")
    p.add_argument("--content")

    p = sub.add_parser("search-docs", help="Search cloud documents")
    p.add_argument("query")
    p.add_argument("--limit", type=int, default=20)

    p = sub.add_parser("search-messages", help="Search chat messages")
    p.add_argument("query")
    p.add_argument("--limit", type=int, default=20)

    p = sub.add_parser("doc", help="Read a docx document's text")
    p.add_argument("document_id")

    p = sub.add_parser("doc-blocks", help="List a document's blocks")
    p.add_argument("document_id")
    p.add_argument("--limit", type=int, default=_DEFAULT_LIMIT)

    p = sub.add_parser("doc-create", help="Create a document")
    p.add_argument("title")
    p.add_argument("--folder-token")

    p = sub.add_parser("wiki-spaces", help="List knowledge spaces")
    p.add_argument("--limit", type=int, default=_DEFAULT_LIMIT)

    p = sub.add_parser("wiki-nodes", help="List a space's nodes")
    p.add_argument("space_id")
    p.add_argument("--limit", type=int, default=_DEFAULT_LIMIT)

    p = sub.add_parser("drive-files", help="List drive files (root if no folder)")
    p.add_argument("--folder-token")
    p.add_argument("--limit", type=int, default=_DEFAULT_LIMIT)

    p = sub.add_parser("download", help="Download a drive file")
    p.add_argument("file_token")
    p.add_argument("-o", "--out", required=True)

    p = sub.add_parser("sheet-values", help="Read a spreadsheet range")
    p.add_argument("spreadsheet_token")
    p.add_argument("range", help="e.g. sheetId!A1:D10")

    p = sub.add_parser("sheet-write", help="Write values to a range")
    p.add_argument("spreadsheet_token")
    p.add_argument("range")
    p.add_argument("values", help="JSON 2D array")

    p = sub.add_parser("bitable-tables", help="List bitable tables")
    p.add_argument("app_token")

    p = sub.add_parser("bitable-records", help="List a bitable table's records")
    p.add_argument("app_token")
    p.add_argument("table_id")
    p.add_argument("--limit", type=int, default=_DEFAULT_LIMIT)

    p = sub.add_parser("bitable-search", help="Search bitable records")
    p.add_argument("app_token")
    p.add_argument("table_id")
    p.add_argument("--body", help="Search request JSON")

    p = sub.add_parser("bitable-create-record", help="Add a bitable record")
    p.add_argument("app_token")
    p.add_argument("table_id")
    p.add_argument("fields", help="JSON object of field values")

    sub.add_parser("tasklists", help="List task lists")

    p = sub.add_parser("tasks", help="List a task list's tasks")
    p.add_argument("tasklist_guid")
    p.add_argument("--limit", type=int, default=_DEFAULT_LIMIT)

    p = sub.add_parser("task-create", help="Create a task")
    p.add_argument("summary")
    p.add_argument("--description")
    p.add_argument("--due", help="ISO 8601 due datetime")

    p = sub.add_parser("task-complete", help="Mark a task done")
    p.add_argument("task_guid")

    sub.add_parser("calendars", help="List calendars")

    p = sub.add_parser("events", help="List calendar events")
    p.add_argument("calendar_id")
    p.add_argument("--start", help="ISO 8601 window start")
    p.add_argument("--end", help="ISO 8601 window end")
    p.add_argument("--limit", type=int, default=_DEFAULT_LIMIT)

    p = sub.add_parser("event-create", help="Create a calendar event")
    p.add_argument("calendar_id")
    p.add_argument("summary")
    p.add_argument("--start", required=True, help="ISO 8601")
    p.add_argument("--end", required=True, help="ISO 8601")
    p.add_argument("--description")
    p.add_argument(
        "--attendee", action="append", default=[], help="open_id, repeatable"
    )

    p = sub.add_parser("user", help="Get a user's profile")
    p.add_argument("user_id")
    p.add_argument(
        "--id-type", default="open_id", choices=["open_id", "union_id", "user_id"]
    )

    p = sub.add_parser("dept-users", help="List a department's users")
    p.add_argument("department_id")
    p.add_argument("--limit", type=int, default=_DEFAULT_LIMIT)

    p = sub.add_parser("resolve-users", help="Map emails to user ids")
    p.add_argument("emails", nargs="+")

    p = sub.add_parser(
        "raw",
        help="Generic call: raw METHOD /open-apis/... [--data JSON] [--param k=v ...]",
    )
    p.add_argument("method", choices=["GET", "POST", "PUT", "PATCH", "DELETE"])
    p.add_argument("path")
    p.add_argument("--data", help="JSON request body")
    p.add_argument(
        "--param", action="append", default=[], help="k=v query param, repeatable"
    )

    return parser


def main() -> None:
    args = _build_parser().parse_args()
    handler = _HANDLERS.get(args.cmd)
    if handler is None:  # unreachable: subparsers are required
        raise SystemExit(f"unknown command {args.cmd}")
    _out(handler(args))


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        sys.exit(0)
