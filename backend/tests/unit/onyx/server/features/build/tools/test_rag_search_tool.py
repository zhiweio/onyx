"""Unit tests for the rag_search platform tool behavior surface: error
containment (the failure text an agent sees), the empty-index wording, and
the user-refresh path in the user-scoped search binding (which must call
Result.unique() because User carries collection joined eager loads)."""

from typing import Any
from unittest.mock import patch

import pytest
from sqlalchemy import select

from onyx.db.models import User
from onyx.server.features.build.tools.base import ToolContext, ToolInvocation
from onyx.server.features.build.tools.implementations import RagSearchTool
from onyx.server.features.build.tools.service_bindings import (
    make_user_scoped_search_fn,
)

CTX = ToolContext(user_id="u1")


def _invoke(query: str) -> ToolInvocation:
    return ToolInvocation(tool="rag_search", arguments={"query": query})


def _text(result: Any) -> str:
    return result.content[0]["text"]


def test_missing_query_is_rejected_without_calling_search() -> None:
    called = []

    def search(*_args: Any) -> list[dict[str, Any]]:
        called.append(1)
        return []

    result = RagSearchTool(search).execute(_invoke("   "), CTX)
    assert _text(result) == "[rag_search] argument 'query' is required"
    assert called == []


def test_search_exception_surfaces_as_tool_error_text(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def boom(*_args: Any) -> list[dict[str, Any]]:
        raise RuntimeError("index exploded")

    result = RagSearchTool(boom).execute(_invoke("年报"), CTX)
    # Agent-facing output stays the failure line; no exception escapes.
    assert _text(result) == "[rag_search] search failed: index exploded"
    # The log is the env-side trace for the same failure.
    assert any("rag_search failed" in rec.message for rec in caplog.records), (
        "rag_search failures must be logged with exc_info for observability"
    )


def test_empty_index_reports_no_documents() -> None:
    result = RagSearchTool(lambda *_: []).execute(_invoke("anything"), CTX)
    assert _text(result) == "[rag_search] no matching documents"


def test_hits_render_numbered_list_with_links() -> None:
    def search(
        _q: str, _sets: list[str], _limit: int, _ctx: ToolContext
    ) -> list[dict[str, Any]]:
        return [
            {"title": "发票管理规范", "blurb": "摘要", "link": "/d/2"},
            {"title": None, "content": "仅内容"},
        ]

    result = RagSearchTool(search).execute(_invoke("发票"), CTX)
    assert "1. 发票管理规范 (/d/2)" in _text(result)
    assert "2. (untitled)" in _text(result)


def test_user_scoped_search_fn_uniques_the_user_refresh() -> None:
    """The refresh `select(User)` must go through Result.unique().

    User has joined eager loads against collections, so scalar accessors
    raise without it — this was the bug that made every rag_search call
    fail with "The unique() method must be invoked on this Result".
    """

    class _FakeResult:
        def __init__(self, value: User | None) -> None:
            self._value = value
            self.uniqued = False

        def unique(self) -> "_FakeResult":
            self.uniqued = True
            return self

        def scalar_one_or_none(self) -> User | None:
            assert self.uniqued, "scalar_one_or_none() called before .unique()"
            return self._value

    user = User(email="probe@example.com")
    captured: dict[str, Any] = {}

    class _FakeSession:
        def __enter__(self) -> "_FakeSession":
            return self

        def __exit__(self, *_args: Any) -> None:
            return None

        def execute(self, stmt: Any) -> _FakeResult:
            captured["stmt"] = stmt
            return _FakeResult(user)

    with (
        patch(
            "onyx.context.search.pipeline.search_pipeline",
            return_value=iter([]),
        ) as pipeline,
        patch(
            "onyx.db.search_settings.get_current_search_settings",
            return_value=None,
        ),
        patch(
            "onyx.document_index.factory.get_default_document_index",
            return_value=None,
        ),
        patch(
            "onyx.db.engine.sql_engine.get_session_with_current_tenant",
            return_value=_FakeSession(),
        ),
    ):
        fn = make_user_scoped_search_fn(user)
        hits = fn("查询", [], 5, CTX)

    assert hits == []
    assert isinstance(captured["stmt"], type(select(User)))
    pipeline.assert_called_once()
