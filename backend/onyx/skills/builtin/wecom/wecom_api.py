#!/usr/bin/env python3
"""WeCom CLI-gateway wrapper for the Onyx Craft sandbox.

Covers the smart-robot (智能机器人) gateway: service discovery, method calls,
media upload, and async-task polling, exposed as subcommands. Output is JSON
on stdout. No auth handling here — the egress proxy injects the bot's bearer
token on the wire; never ask for or handle tokens.

The gateway speaks a flat envelope: HTTP 200 + ``{"errcode": <int>, "errmsg":
"..."}"`` with the business result serialized inside ``results_json`` (often
doubly nested JSON strings). This helper unwraps it; a nonzero ``errcode``
surfaces as ``{"ok": false, "errcode": ..., "errmsg": ...}`` (853004/853005
mean the cached token expired — just retry the call).

Method request fields come from the schema: run ``services <name>`` first —
every method lists its request properties, path, and description.
"""

import argparse
import json
import os
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Any

_BASE = "https://qyapi.weixin.qq.com/cli"
_HTTP_TIMEOUT_SECONDS = 180
_CACHE_TTL_SECONDS = 600

# Service names seen on the gateway; `services` with no argument lists them.
KNOWN_SERVICES = (
    "calendar",
    "chat",
    "contact",
    "disk",
    "doc",
    "identity",
    "mail",
    "media",
    "message",
    "meeting",
    "sheet",
    "smartpage",
    "smartsheet",
    "todo",
)


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


def _unwrap(value: Any) -> Any:
    """Peel the gateway's nested-JSON layers: results_json (str) →
    {"result": str|obj} → result → possibly another JSON string."""
    for _ in range(4):
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except ValueError:
                return value
        if isinstance(value, dict) and set(value) == {"result"}:
            value = value["result"]
            continue
        return value
    return value


def _poll_long_task(
    path: str, taskid: str, poll_mode: int, max_polls: int = 60
) -> dict[str, Any]:
    """Drain a long-task (``taskid``) response.

    The gateway runs two poll protocols (mirrors the official CLI's
    transport): mode 0 re-POSTs ``/task/query`` with the flat
    ``PollClawLongTask`` body; mode 1 re-POSTs the *original* endpoint with
    an empty JSON body and the taskid in ``X-Long-Poll-TaskId``.
    """
    poll_body = {
        "payload": json.dumps(
            {
                "method": "PollClawLongTask",
                "payload": json.dumps({"taskid": taskid}),
            }
        )
    }

    def _one_poll(
        poll_path: str, body: dict[str, Any], extra: dict[str, str]
    ) -> tuple[Any, str, str]:
        req = urllib.request.Request(  # noqa: S310 — fixed https base url
            _BASE + poll_path,
            data=json.dumps(body).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json; charset=utf-8", **extra},
        )
        try:
            with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT_SECONDS) as resp:  # noqa: S310
                envelope = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:2000]
            return None, str(exc.code), detail
        except urllib.error.URLError as exc:
            return None, "network", str(exc.reason)
        errcode = envelope.get("errcode")
        if errcode not in (None, 0):
            return None, str(errcode), str(envelope.get("errmsg") or "")
        inner = _unwrap(envelope.get("results_json"))
        return (inner if isinstance(inner, dict) else {}), "", ""

    for _ in range(max_polls):
        if poll_mode == 1:
            inner, code, msg = _one_poll(path, {}, {"X-Long-Poll-TaskId": taskid})
        else:
            inner, code, msg = _one_poll("/task/query", poll_body, {})
        if inner is None:
            return {"ok": False, "errcode": code, "msg": msg}
        # Termination: long_task_poll.done wins over taskid presence —
        # mode-1 rounds keep returning the SAME taskid while done flips.
        poll_state = inner.get("long_task_poll") or {}
        if poll_state.get("done"):
            result = _unwrap(inner.get("result"))
        elif not inner.get("taskid"):
            result = _unwrap(inner)
        else:
            taskid = str(inner["taskid"])
            time.sleep(float(poll_state.get("polling_interval_ms") or 1000) / 1000.0)
            continue
        if isinstance(result, dict):
            result.pop("security_notice", None)
            result.pop("extra_identity_context", None)
            return result
        return {"ok": True, "result": result}
        time.sleep(float(poll_state.get("polling_interval_ms") or 1000) / 1000.0)
    return {"ok": False, "msg": f"long task {taskid[:16]} polling timed out"}


def _gateway_call(
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """One CLI-gateway request with the payload-string envelope.

    The Authorization header is injected by the egress proxy; never set it
    here. Returns the unwrapped business result, or {"ok": False, ...}.
    Long-task deferrals (``poll_mode``/``taskid``) are polled automatically.
    """
    url = _BASE + path
    body = json.dumps(
        {"payload": json.dumps(payload or {}, ensure_ascii=False)}
    ).encode("utf-8")
    req = urllib.request.Request(  # noqa: S310 — fixed https base url
        url,
        data=body if method in ("POST", "PUT", "PATCH") else None,
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

    errcode = envelope.get("errcode")
    if errcode not in (None, 0):
        return {
            "ok": False,
            "errcode": errcode,
            "errmsg": envelope.get("errmsg"),
            # Surface the raw payload too: some errors carry recovery hints.
            "result": _unwrap(envelope.get("results_json")),
        }
    result = _unwrap(envelope.get("results_json"))
    if result is None:
        return {"ok": True}
    if isinstance(result, dict) and result.get("taskid"):
        poll_mode = int(result.get("poll_mode") or 0)
        del method
        return _poll_long_task(path, str(result["taskid"]), poll_mode)
    if isinstance(result, dict):
        # Server-injected prompt blocks are platform metadata, not content.
        result.pop("security_notice", None)
        result.pop("extra_identity_context", None)
    return result


def _upload(path: str, file_path: str, field: str = "media") -> dict[str, Any]:
    """Multipart upload (gateway media endpoints). Returns media metadata."""
    boundary = f"----onyx{int(time.time() * 1000)}"
    filename = os.path.basename(file_path)
    try:
        with open(file_path, "rb") as fh:
            content = fh.read()
    except OSError as exc:
        return {"ok": False, "msg": str(exc)}
    parts = [
        f"--{boundary}",
        'Content-Disposition: form-data; name="type"',
        "",
        "file",
        f"--{boundary}",
        f'Content-Disposition: form-data; name="{field}"; filename="{filename}"',
        "Content-Type: application/octet-stream",
        "",
    ]
    body = (
        ("\r\n".join(parts) + "\r\n").encode("utf-8")
        + content
        + f"\r\n--{boundary}--\r\n".encode()
    )
    req = urllib.request.Request(  # noqa: S310 — fixed https base url
        _BASE + path,
        data=body,
        method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT_SECONDS) as resp:  # noqa: S310
            envelope = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:2000]
        return {"ok": False, "http_status": exc.code, "msg": detail}
    except urllib.error.URLError as exc:
        return {"ok": False, "msg": str(exc.reason)}
    if envelope.get("errcode") not in (None, 0):
        return {
            "ok": False,
            "errcode": envelope.get("errcode"),
            "errmsg": envelope.get("errmsg"),
        }
    return envelope


# ---------------------------------------------------------------------------
# Schema cache: discovery results are stable for minutes; cache to /tmp.
# ---------------------------------------------------------------------------


def _cache_path() -> str:
    return os.path.join(tempfile.gettempdir(), "onyx_wecom_services.json")


def _load_cache(max_age: int) -> dict[str, Any] | None:
    try:
        stat = os.stat(_cache_path())
        if time.time() - stat.st_mtime > max_age:
            return None
        with open(_cache_path(), encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def _store_cache(services: dict[str, Any]) -> None:
    try:
        with open(_cache_path(), "w", encoding="utf-8") as fh:
            json.dump(services, fh, ensure_ascii=False)
    except OSError:
        pass


def _service_schema(service: str) -> dict[str, Any] | None:
    """The service's discovery schema ({"methods", "resources", "schemas"})."""
    result = _gateway_call("POST", "/service/discovery", {"service": service})
    if isinstance(result, dict) and result.get("ok") is False:
        return None
    return result if isinstance(result, dict) else None


def _flatten_methods(prefix: str, node: dict[str, Any], out: dict[str, Any]) -> None:
    for name, method in (node.get("methods") or {}).items():
        out[prefix + name] = method
    for name, sub in (node.get("resources") or {}).items():
        _flatten_methods(
            prefix + name + ".",
            {"methods": sub.get("methods"), "resources": sub.get("resources")},
            out,
        )


def _summarize_schema_ref(ref: Any, schemas: dict[str, Any], depth: int = 0) -> Any:
    """Resolve a {"$ref": Name} into a compact {prop: type} view."""
    if not isinstance(ref, dict):
        return ref
    name = ref.get("$ref")
    if not name:
        return ref
    schema = schemas.get(name) if isinstance(schemas, dict) else None
    if not isinstance(schema, dict):
        return name
    props = schema.get("properties")
    if not isinstance(props, dict) or depth > 1:
        return name
    summary: dict[str, Any] = {}
    for prop, spec in props.items():
        if not isinstance(spec, dict):
            continue
        prop_type = spec.get("type")
        if prop_type is None and "$ref" in spec:
            prop_type = str(spec.get("$ref"))
        desc = spec.get("description") or ""
        summary[prop] = f"{prop_type}: {desc}".strip(": ")
    return summary


def _describe_methods(service: str) -> dict[str, Any]:
    schema = _service_schema(service)
    if schema is None:
        return {"ok": False, "msg": f"service '{service}' not found"}
    methods: dict[str, Any] = {}
    _flatten_methods("", schema, methods)
    schemas = schema.get("schemas") or {}
    out: dict[str, Any] = {}
    for name, method in sorted(methods.items()):
        out[name] = {
            "method": method.get("http_method"),
            "path": method.get("path"),
            "request": _summarize_schema_ref(method.get("request"), schemas),
            "description": method.get("description"),
        }
    return {
        "service": service,
        "description": schema.get("description"),
        "methods": out,
    }


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------


def _cmd_services(a: argparse.Namespace) -> dict[str, Any]:
    if not a.service:
        cached = _load_cache(_CACHE_TTL_SECONDS)
        if cached and "directory" in cached:
            return cached["directory"]
        result = _gateway_call("POST", "/service/discovery", {})
        if isinstance(result, dict) and result.get("ok") is False:
            return result
        items = result.get("items") if isinstance(result, dict) else None
        directory = [
            {"name": i.get("name"), "description": i.get("description")}
            for i in (items or [])
            if isinstance(i, dict) and not i.get("hidden")
        ]
        _store_cache({**(_load_cache(1 << 30) or {}), "directory": directory})
        return directory
    return _describe_methods(a.service)


def _resolve_method(service: str, dotted: str) -> tuple[str, str] | dict[str, Any]:
    """``(http_method, path)`` for ``service resource.method``, or an error
    dict. Uses the schema cache so repeated calls don't re-discover."""
    cache = _load_cache(_CACHE_TTL_SECONDS) or {}
    schema = cache.get(service)
    if not isinstance(schema, dict):
        schema = _service_schema(service)
        if schema is None:
            return {"ok": False, "msg": f"service '{service}' not found"}
        _store_cache({**cache, service: schema})
    methods: dict[str, Any] = {}
    _flatten_methods("", schema, methods)
    method = methods.get(dotted)
    if not isinstance(method, dict):
        return {
            "ok": False,
            "msg": f"method '{dotted}' not found in service '{service}'",
            "known": sorted(methods),
        }
    return str(method.get("http_method") or "POST"), str(method.get("path") or "")


def _cmd_call(a: argparse.Namespace) -> dict[str, Any]:
    resolved = _resolve_method(a.service, a.dotted)
    if isinstance(resolved, dict):
        return resolved
    method, path = resolved
    payload = json.loads(a.data) if a.data else {}
    return _gateway_call(method, path, payload)


def _cmd_raw(a: argparse.Namespace) -> dict[str, Any]:
    payload = json.loads(a.data) if a.data else {}
    return _gateway_call(a.method, a.path, payload)


def _cmd_upload(a: argparse.Namespace) -> dict[str, Any]:
    return _upload(a.path, a.file, field=a.field)


def _cmd_task(a: argparse.Namespace) -> dict[str, Any]:
    return _poll_long_task(a.path, a.task_id, a.mode)


def _cmd_download(a: argparse.Namespace) -> dict[str, Any]:
    """Download by media_id via /media/download; long-task deferrals poll
    automatically inside _gateway_call."""
    return _gateway_call("POST", "/media/download", {"media_id": a.media_id})


_HANDLERS: dict[str, Callable[[argparse.Namespace], dict[str, Any]]] = {
    "services": _cmd_services,
    "call": _cmd_call,
    "raw": _cmd_raw,
    "upload": _cmd_upload,
    "task": _cmd_task,
    "download": _cmd_download,
}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser(
        "services", help="List gateway services, or one service's methods"
    )
    p.add_argument(
        "--service",
        help=f"Service name ({', '.join(KNOWN_SERVICES)}); omit for the directory",
    )

    p = sub.add_parser("call", help="Invoke a service method by dotted name")
    p.add_argument("service", help="e.g. calendar")
    p.add_argument("dotted", help="e.g. schedules.create (see `services --service`)")
    p.add_argument("--data", help="JSON request payload")

    p = sub.add_parser(
        "raw", help="Generic call: raw POST /path --data JSON (path under /cli)"
    )
    p.add_argument("method", choices=["GET", "POST", "PUT", "PATCH", "DELETE"])
    p.add_argument("path", help="e.g. /calendar/schedules/list")
    p.add_argument("--data", help="JSON request payload")

    p = sub.add_parser("upload", help="Upload a media file (multipart)")
    p.add_argument("file")
    p.add_argument("--path", default="/file/upload", help="default /file/upload")
    p.add_argument("--field", default="media", help="multipart field name")

    p = sub.add_parser("task", help="Poll an async gateway task")
    p.add_argument("task_id")
    p.add_argument(
        "--path",
        default="/task/query",
        help="Origin endpoint for mode-1 (reuse-endpoint) tasks",
    )
    p.add_argument(
        "--mode",
        type=int,
        default=0,
        choices=[0, 1],
        help="poll_mode from the response",
    )

    p = sub.add_parser("download", help="Download a media file by media_id")
    p.add_argument("media_id")

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
