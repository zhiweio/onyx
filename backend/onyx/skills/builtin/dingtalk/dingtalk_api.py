#!/usr/bin/env python3
"""DingTalk new-gen OpenAPI wrapper for the Onyx Craft sandbox.

Covers the ``api.dingtalk.com`` REST surface as named routes (knowledge base,
drive, todo, calendar, contacts, robot, AI cards) plus a generic ``raw``
escape hatch, with cursor pagination for the list endpoints. Output is JSON
on stdout. No auth handling here — the egress proxy injects the corp access
token as ``x-acs-dingtalk-access-token``; never ask for or handle tokens.

Routes are static (DingTalk has no service discovery): run
``dingtalk_api.py routes`` to list them. Path placeholders (``{unionId}``,
``{spaceId}``, ...) are filled from ``--data`` fields and removed from the
payload; remaining GET fields become query params, non-GET fields the JSON
body.
"""

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Any

_BASE = "https://api.dingtalk.com"
_HTTP_TIMEOUT_SECONDS = 60
_MAX_PAGES = 20

# Dotted route name → (HTTP method, path template). Mirrors the provider
# catalog; anything else goes through `raw` (gated by the same catalog).
ROUTES: dict[str, tuple[str, str]] = {
    "kb.list": ("GET", "/v2.0/wiki/workspaces"),
    "kb.nodes": ("GET", "/v2.0/wiki/nodes"),
    "kb.content": ("GET", "/v1.0/doc/suites/documents/{docKey}/blocks"),
    "drive.spaces": ("GET", "/v1.0/drive/spaces"),
    "drive.files": ("GET", "/v1.0/drive/spaces/{spaceId}/files"),
    "drive.download": (
        "GET",
        "/v1.0/drive/spaces/{spaceId}/files/{fileId}/downloadUrl",
    ),
    "todo.list": ("GET", "/v1.0/todo/users/{unionId}/tasks"),
    "todo.get": ("GET", "/v1.0/todo/users/{unionId}/tasks/{taskId}"),
    "todo.create": ("POST", "/v1.0/todo/users/{unionId}/tasks"),
    "todo.update": ("PUT", "/v1.0/todo/users/{unionId}/tasks/{taskId}"),
    "todo.delete": ("DELETE", "/v1.0/todo/users/{unionId}/tasks/{taskId}"),
    "calendar.events": (
        "GET",
        "/v1.0/calendar/users/{userId}/calendars/{calendarId}/events",
    ),
    "calendar.event": (
        "GET",
        "/v1.0/calendar/users/{userId}/calendars/{calendarId}/events/{eventId}",
    ),
    "calendar.create": (
        "POST",
        "/v1.0/calendar/users/{userId}/calendars/{calendarId}/events",
    ),
    "calendar.update": (
        "PUT",
        "/v1.0/calendar/users/{userId}/calendars/{calendarId}/events/{eventId}",
    ),
    "calendar.delete": (
        "DELETE",
        "/v1.0/calendar/users/{userId}/calendars/{calendarId}/events/{eventId}",
    ),
    "contact.user": ("GET", "/v1.0/contact/users/{unionId}"),
    "contact.search": ("POST", "/v1.0/contact/users/search"),
    "robot.o2o": ("POST", "/v1.0/robot/oToMessages/batchSend"),
    "robot.group": ("POST", "/v1.0/robot/groupMessages/send"),
    "card.create": ("POST", "/v1.0/card/instances"),
    "card.deliver": ("POST", "/v1.0/card/instances/deliver"),
    "card.stream": ("PUT", "/v1.0/card/streaming"),
}

# Key the list endpoints nest their items under, checked in order.
_LIST_KEYS = (
    "workspaces",
    "knowledgeBases",
    "nodes",
    "files",
    "taskList",
    "events",
    "list",
)
_CURSOR_KEYS = ("nextToken", "nextCursor")
# Cursor values meaning "no more pages" (DingTalk: -1; 0 only terminates
# after page one, where it is the start token).
_DONE_CURSORS = (None, "", -1, "-1")


def _prune(value: Any) -> Any:
    """Recursively drop None / "" / [] / {} so LLM-facing output stays
    small. Booleans and 0 are kept — they carry signal."""
    if isinstance(value, dict):
        out = {k: _prune(v) for k, v in value.items()}
        return {k: v for k, v in out.items() if v not in (None, "", [], {})}
    if isinstance(value, list):
        return [_prune(v) for v in value]
    return value


def _out(value: Any) -> None:
    print(json.dumps(_prune(value), ensure_ascii=False, indent=2))


def _request(method: str, path: str, params: dict[str, Any] | None) -> dict[str, Any]:
    """One API call. GET params ride the query string, anything else the JSON
    body. The auth header is injected by the egress proxy; never set it here."""
    query = urllib.parse.urlencode(params) if method == "GET" and params else ""
    url = _BASE + path + (f"?{query}" if query else "")
    data = (
        json.dumps(params, ensure_ascii=False).encode("utf-8")
        if method != "GET" and params
        else None
    )
    req = urllib.request.Request(  # noqa: S310 — fixed https base url
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    try:
        with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT_SECONDS) as resp:  # noqa: S310
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:2000]
        try:
            parsed = json.loads(detail)
        except ValueError:
            parsed = detail
        return {
            "ok": False,
            "http_status": exc.code,
            "error": parsed,
        }
    except urllib.error.URLError as exc:
        return {"ok": False, "msg": str(exc.reason)}
    if not body:
        return {"ok": True}
    try:
        result = json.loads(body)
    except ValueError:
        return {"ok": True, "result": body}
    if isinstance(result, dict):
        errcode = result.get("errcode")
        if errcode not in (None, 0):
            return {"ok": False, "errcode": errcode, "errmsg": result.get("errmsg")}
    return {"ok": True, "result": result}


def _find_list(value: dict[str, Any]) -> str | None:
    for key in _LIST_KEYS:
        if isinstance(value.get(key), list):
            return key
    return None


def _find_cursor(value: dict[str, Any]) -> tuple[str, Any] | None:
    """``(cursor_key, cursor_value)`` or None; the key is echoed back so the
    API's own spelling is reused on the next page."""
    for key in _CURSOR_KEYS:
        if key in value:
            return key, value[key]
    return None


def _call_paginated(method: str, path: str, params: dict[str, Any]) -> dict[str, Any]:
    """GET a list endpoint until the cursor runs out, merging the item lists.
    Non-list results (or a first page that fails) return unchanged."""
    merged_key: str | None = None
    merged: list[Any] = []
    last: dict[str, Any] = {}
    seen: set[Any] = set()
    for _ in range(_MAX_PAGES):
        page = _request(method, path, params)
        if page.get("ok") is not True:
            return page
        result = page.get("result")
        if not isinstance(result, dict):
            return page
        last = result
        list_key = _find_list(result)
        if list_key is None:
            return page
        merged_key = merged_key or list_key
        if list_key == merged_key:
            merged.extend(result[list_key])
        found = _find_cursor(result)
        if found is None or found[1] in _DONE_CURSORS or found[1] in seen:
            break
        cursor_key, cursor = found
        seen.add(cursor)
        params = {**params, cursor_key: cursor}
    out = {k: v for k, v in last.items() if not isinstance(v, list)}
    out[merged_key or "items"] = merged
    return {"ok": True, "result": out}


def _split_params(
    path_template: str, params: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    """Fill ``{name}`` path placeholders from ``params`` (popping them) and
    return the concrete path plus the remaining payload."""
    path = path_template
    for name in [
        seg[1:-1]
        for seg in path.split("/")
        if seg.startswith("{") and seg.endswith("}")
    ]:
        if name not in params:
            raise SystemExit(f"missing path parameter {name!r} in --data")
        path = path.replace(
            "{%s}" % name, urllib.parse.quote(str(params.pop(name)), safe="")
        )
    return path, params


def _cmd_routes(_: argparse.Namespace) -> dict[str, Any]:
    return {name: {"method": m, "path": p} for name, (m, p) in sorted(ROUTES.items())}


def _cmd_call(a: argparse.Namespace) -> dict[str, Any]:
    route = ROUTES.get(a.route)
    if route is None:
        return {
            "ok": False,
            "msg": f"unknown route {a.route!r}",
            "known": sorted(ROUTES),
        }
    method, template = route
    params = json.loads(a.data) if a.data else {}
    path, params = _split_params(template, params)
    if a.paginate:
        if method != "GET":
            return {"ok": False, "msg": "--paginate only applies to GET routes"}
        return _call_paginated(method, path, params)
    return _request(method, path, params)


def _cmd_raw(a: argparse.Namespace) -> dict[str, Any]:
    params = json.loads(a.data) if a.data else {}
    if a.paginate:
        if a.method != "GET":
            return {"ok": False, "msg": "--paginate only applies to GET"}
        return _call_paginated(a.method, a.path, params)
    return _request(a.method, a.path, params)


_HANDLERS: dict[str, Callable[[argparse.Namespace], dict[str, Any]]] = {
    "routes": _cmd_routes,
    "call": _cmd_call,
    "raw": _cmd_raw,
}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("routes", help="List the named routes")

    p = sub.add_parser("call", help="Invoke a named route (see `routes`)")
    p.add_argument("route", help="e.g. kb.nodes, drive.files, todo.list")
    p.add_argument("--data", help="JSON payload: path params + query/body fields")
    p.add_argument(
        "--paginate", action="store_true", help="Follow the cursor and merge list pages"
    )

    p = sub.add_parser("raw", help="Generic call: raw GET /v1.0/... --data JSON")
    p.add_argument("method", choices=["GET", "POST", "PUT", "PATCH", "DELETE"])
    p.add_argument("path", help="e.g. /v2.0/wiki/workspaces")
    p.add_argument("--data", help="JSON payload (query for GET, body otherwise)")
    p.add_argument("--paginate", action="store_true", help="Follow the cursor")

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
