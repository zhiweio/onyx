"""Unit tests for the WeCom CLI-gateway connectors (mocked HTTP): the signed
token bootstrap, envelope unwrapping with one retry on a dead token, and the
wecom_docs / wecom_im connectors over the gateway."""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any

import pytest
from requests_mock import Mocker as RequestsMocker

from onyx.connectors.exceptions import CredentialInvalidError
from onyx.connectors.models import Document
from onyx.connectors.wecom._gateway import WeComGatewayClient
from onyx.connectors.wecom_docs.connector import WeComDocsConnector
from onyx.connectors.wecom_im.connector import WeComImConnector

BOT_CREDS = {"wecom_bot_id": "aibnBOT", "wecom_bot_secret": "bot-secret"}
_TOKEN_URL = "https://qyapi.weixin.qq.com/cgi-bin/aibot/cli/get_cli_config"
_GATEWAY = "https://qyapi.weixin.qq.com/cli"


def _gateway_body(payload: dict[str, Any]) -> dict[str, Any]:
    """The gateway's flat envelope with its (doubly) serialized result."""
    return {
        "errcode": 0,
        "errmsg": "ok",
        "results_json": json.dumps({"result": json.dumps(payload)}),
    }


def _register_token(requests_mock: RequestsMocker, calls: list[dict[str, Any]]) -> None:
    def _token_callback(request: Any, _context: Any) -> dict[str, Any]:
        body = request.json()
        calls.append(body)
        expected = hashlib.sha256(
            f"bot-secret{body['bot_id']}{body['time']}{body['nonce']}".encode()
        ).hexdigest()
        assert body["bot_id"] == "aibnBOT"
        assert body["bind_source"] == 1
        assert body["signature"] == expected
        return {"errcode": 0, "token": "tok-1"}

    requests_mock.post(_TOKEN_URL, json=_token_callback)


def test_gateway_client_signs_and_unwraps(
    requests_mock: RequestsMocker,
) -> None:
    token_calls: list[dict[str, Any]] = []
    _register_token(requests_mock, token_calls)
    requests_mock.post(
        f"{_GATEWAY}/identity/whoami",
        json=_gateway_body({"userid": "wo1", "name": "Onyx"}),
    )

    client = WeComGatewayClient(
        BOT_CREDS["wecom_bot_id"], BOT_CREDS["wecom_bot_secret"]
    )
    result = client.call("/identity/whoami", {})
    assert result == {"userid": "wo1", "name": "Onyx"}
    assert len(token_calls) == 1


def test_gateway_client_retries_once_on_dead_token(
    requests_mock: RequestsMocker,
) -> None:
    token_calls: list[dict[str, Any]] = []
    _register_token(requests_mock, token_calls)
    # First attempt hits a dead token, the retry after re-bootstrap succeeds.
    requests_mock.post(
        f"{_GATEWAY}/chat/groups/list",
        [
            {"json": {"errcode": 853005, "errmsg": "cli token invalid"}},
            {"json": _gateway_body({"chats": [], "has_more": False})},
        ],
    )

    client = WeComGatewayClient(
        BOT_CREDS["wecom_bot_id"], BOT_CREDS["wecom_bot_secret"]
    )
    result = client.call("/chat/groups/list", {"begin_time": "x", "end_time": "y"})
    assert result == {"chats": [], "has_more": False}
    assert len(token_calls) == 2  # bootstrap + refresh


def test_gateway_client_surfaces_business_error(
    requests_mock: RequestsMocker,
) -> None:
    from onyx.connectors.china_common import ChinaConnectorError

    token_calls: list[dict[str, Any]] = []
    _register_token(requests_mock, token_calls)
    requests_mock.post(
        f"{_GATEWAY}/chat/groups/list",
        json={"errcode": 850016, "errmsg": "begin_time不能早于7天前"},
    )

    client = WeComGatewayClient(
        BOT_CREDS["wecom_bot_id"], BOT_CREDS["wecom_bot_secret"]
    )
    with pytest.raises(ChinaConnectorError, match="850016"):
        client.call("/chat/groups/list", {})


def test_gateway_client_polls_mode1_long_task(
    requests_mock: RequestsMocker,
) -> None:
    """poll_mode=1 re-POSTs the original endpoint with an empty body and the
    taskid in X-Long-Poll-TaskId until the response stops carrying one."""
    token_calls: list[dict[str, Any]] = []
    _register_token(requests_mock, token_calls)

    state = {"done": False}

    def _deferred(request: Any, _context: Any) -> dict[str, Any]:
        task_header = request.headers.get("X-Long-Poll-TaskId")
        if task_header == "task-7":
            # Poll rounds: the SAME taskid rides along while done flips false
            # -> true; termination must key off done, not the taskid.
            assert request.json() == {}
            done = state["done"]
            state["done"] = True
            return {
                "errcode": 0,
                "results_json": json.dumps(
                    {
                        "result": json.dumps({"content": "# done", "name": "doc"})
                        if done
                        else "{}",
                        "taskid": "task-7",
                        "poll_mode": 1,
                        "long_task_poll": (
                            {"done": True}
                            if done
                            else {"done": False, "polling_interval_ms": 1}
                        ),
                    }
                ),
            }
        # Initial call with the business payload defers to a long task.
        assert request.json() == {"payload": json.dumps({"docid": "D1"})}
        return {
            "errcode": 0,
            "results_json": json.dumps(
                {"result": "{}", "taskid": "task-7", "poll_mode": 1}
            ),
        }

    requests_mock.post(f"{_GATEWAY}/doc/contents/get", json=_deferred)

    client = WeComGatewayClient(
        BOT_CREDS["wecom_bot_id"], BOT_CREDS["wecom_bot_secret"]
    )
    result = client.call("/doc/contents/get", {"docid": "D1"})
    assert result == {"content": "# done", "name": "doc"}


def test_gateway_client_polls_mode0_long_task(
    requests_mock: RequestsMocker,
) -> None:
    """poll_mode=0 drains via /task/query with the flat PollClawLongTask body
    (itself riding the payload-string envelope)."""
    token_calls: list[dict[str, Any]] = []
    _register_token(requests_mock, token_calls)
    requests_mock.post(
        f"{_GATEWAY}/doc/import",
        json={
            "errcode": 0,
            "results_json": json.dumps(
                {"result": "{}", "taskid": "task-1", "poll_mode": 0}
            ),
        },
    )

    def _poll(request: Any, _context: Any) -> dict[str, Any]:
        inner = json.loads(request.json()["payload"])
        assert inner["method"] == "PollClawLongTask"
        assert json.loads(inner["payload"]) == {"taskid": "task-1"}
        return _gateway_body(
            {
                "result": json.dumps({"task_status": "succ"}),
                "long_task_poll": {"done": True},
            }
        )

    requests_mock.post(f"{_GATEWAY}/task/query", json=_poll)

    client = WeComGatewayClient(
        BOT_CREDS["wecom_bot_id"], BOT_CREDS["wecom_bot_secret"]
    )
    result = client.call("/doc/import", {})
    assert result == {"task_status": "succ"}


def test_docs_connector_indexes_doc_and_sheet(
    requests_mock: RequestsMocker,
) -> None:
    token_calls: list[dict[str, Any]] = []
    _register_token(requests_mock, token_calls)
    requests_mock.post(
        f"{_GATEWAY}/doc/search",
        json=_gateway_body(
            {
                "docs": [
                    {
                        "docid": "DOC1",
                        "doc_name": "周报",
                        "doc_type": "doc",
                        "modify_time": "2026-10-05 10:00:00",
                        "creator_name": "王志伟",
                    },
                    {
                        "docid": "SHEET1",
                        "doc_name": "预算",
                        "doc_type": "sheet",
                        "modify_time": "2026-10-04 09:00:00",
                    },
                ],
                "has_more": False,
            }
        ),
    )
    requests_mock.post(
        f"{_GATEWAY}/doc/contents/get",
        json=_gateway_body({"content": "# 周报\n内容", "name": "周报"}),
    )
    requests_mock.post(
        f"{_GATEWAY}/sheet/get",
        json=_gateway_body(
            {"name": "预算", "sheets": [{"sheet_id": "s1", "title": "Q4"}]}
        ),
    )
    requests_mock.post(
        f"{_GATEWAY}/sheet/ranges/get",
        json=_gateway_body({"content": "item,qty\n笔,10"}),
    )

    connector = WeComDocsConnector(keywords=["周报"])
    connector.load_credentials(BOT_CREDS)
    docs = [
        doc
        for batch in connector.load_from_state()
        for doc in batch
        if isinstance(doc, Document)
    ]

    by_id = {doc.id: doc for doc in docs}
    assert set(by_id) == {"wecom-docs-DOC1", "wecom-docs-SHEET1"}
    doc_text = by_id["wecom-docs-DOC1"].sections[0].text or ""
    sheet_text = by_id["wecom-docs-SHEET1"].sections[0].text or ""
    assert "# 周报" in doc_text
    assert "item,qty" in sheet_text
    assert by_id["wecom-docs-DOC1"].source.value == "wecom_docs"


def test_docs_connector_explicit_ids_skips_unreadable(
    requests_mock: RequestsMocker,
) -> None:
    token_calls: list[dict[str, Any]] = []
    _register_token(requests_mock, token_calls)
    requests_mock.post(
        f"{_GATEWAY}/doc/contents/get",
        status_code=200,
        json={"errcode": 301006, "errmsg": "no permission"},
    )

    connector = WeComDocsConnector(doc_ids=["GONE"])
    connector.load_credentials(BOT_CREDS)
    assert list(connector.load_from_state()) == []


def test_docs_connector_bad_bot_credentials(
    requests_mock: RequestsMocker,
) -> None:
    def _reject(request: Any, _context: Any) -> dict[str, Any]:
        del request
        return {
            "errcode": 60020,
            "errmsg": "not allowed",
        }

    requests_mock.post(_TOKEN_URL, json=_reject)
    connector = WeComDocsConnector(doc_ids=["X"])
    connector.load_credentials(BOT_CREDS)
    with pytest.raises(CredentialInvalidError):
        connector.validate_connector_settings()


def test_im_connector_groups_messages_by_cst_day(
    requests_mock: RequestsMocker,
) -> None:
    token_calls: list[dict[str, Any]] = []
    _register_token(requests_mock, token_calls)
    now = time.time()
    today_key = time.strftime("%Y%m%d", time.localtime(now))
    requests_mock.post(
        f"{_GATEWAY}/chat/groups/list",
        json=_gateway_body(
            {
                "chats": [{"chat_id": "wrJDc1", "chat_name": "研发群", "msg_count": 3}],
                "has_more": False,
            }
        ),
    )
    requests_mock.post(
        f"{_GATEWAY}/chat/messages/list",
        json=_gateway_body(
            {
                "messages": [
                    {
                        "msg_type": "text",
                        "text": {"content": "发布了吗"},
                        "send_time": int(now) - 60,
                        "userid": "wo1",
                        "user_name": "王志伟",
                    },
                    {
                        "msg_type": "image",
                        "send_time": int(now) - 30,
                        "userid": "wo2",
                        "user_name": "李四",
                    },
                ],
                "has_more": False,
            }
        ),
    )

    connector = WeComImConnector(history_days=30)  # clamped to the 7-day cap
    assert connector.history_days == 7
    connector.load_credentials(BOT_CREDS)
    docs = [
        doc
        for batch in connector.load_from_state()
        for doc in batch
        if isinstance(doc, Document)
    ]

    assert [doc.id for doc in docs] == [f"wecom-im-wrJDc1-{today_key}"]
    text = docs[0].sections[0].text or ""
    assert "王志伟: 发布了吗" in text
    assert "李四: [image]" in text
