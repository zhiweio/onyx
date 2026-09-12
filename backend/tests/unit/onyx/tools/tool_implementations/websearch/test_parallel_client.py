from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock

import httpx
import parallel
import pytest
from fastapi import HTTPException

from onyx.tools.tool_implementations.web_search.clients.parallel_client import (
    ParallelClient,
)
from onyx.tools.tool_implementations.web_search.models import WebSearchResult


class _FakeSearchResult:
    def __init__(
        self,
        *,
        url: str | None,
        title: str | None = None,
        excerpts: list[str] | None = None,
        publish_date: str | None = None,
    ) -> None:
        self.url = url
        self.title = title
        self.excerpts = excerpts
        self.publish_date = publish_date


def _client_with_mocked_search(
    mock_search: Any, *, num_results: int = 5
) -> ParallelClient:
    client = ParallelClient(api_key="test-key", num_results=num_results)
    client._client.search = mock_search  # noqa: SLF001
    return client


def test_search_maps_parallel_response() -> None:
    mock_search = MagicMock(
        return_value=MagicMock(
            results=[
                _FakeSearchResult(
                    url="https://example.com/one",
                    title="Result 1",
                    excerpts=["Snippet A", "Snippet B"],
                    publish_date="2026-03-01",
                ),
                _FakeSearchResult(
                    url=None,
                    title="Result without URL",
                    excerpts=["Should be skipped"],
                ),
            ]
        )
    )
    client = _client_with_mocked_search(mock_search)

    results = client.search("Find latest Parallel Search API docs")

    assert mock_search.call_args.kwargs["objective"] == (
        "Find latest Parallel Search API docs"
    )
    assert mock_search.call_args.kwargs["search_queries"] == [
        "Find latest Parallel Search API docs"
    ]
    assert mock_search.call_args.kwargs["mode"] == "fast"
    assert mock_search.call_args.kwargs["advanced_settings"] == {"max_results": 5}

    assert len(results) == 1
    assert results[0].title == "Result 1"
    assert results[0].link == "https://example.com/one"
    assert results[0].snippet == "Snippet A\nSnippet B"
    assert results[0].published_date == datetime(2026, 3, 1, tzinfo=timezone.utc)


def test_search_rejects_empty_query() -> None:
    client = ParallelClient(api_key="test-key")
    with pytest.raises(ValueError, match="must not be empty"):
        client.search("   ")


def _error_response(status_code: int) -> httpx.Response:
    return httpx.Response(
        status_code,
        request=httpx.Request("POST", "https://api.parallel.ai/v1/search"),
    )


def test_test_connection_maps_invalid_key_errors() -> None:
    client = ParallelClient(api_key="test-key")

    def _mock_search(query: str) -> list[WebSearchResult]:  # noqa: ARG001
        raise parallel.AuthenticationError(
            "Unauthorized",
            response=_error_response(401),
            body=None,
        )

    client.search = _mock_search  # ty: ignore[invalid-assignment]

    with pytest.raises(HTTPException, match="Invalid Parallel API key"):
        client.test_connection()


def test_test_connection_maps_rate_limit_errors() -> None:
    client = ParallelClient(api_key="test-key")

    def _mock_search(query: str) -> list[WebSearchResult]:  # noqa: ARG001
        raise parallel.RateLimitError(
            "Too many requests",
            response=_error_response(429),
            body=None,
        )

    client.search = _mock_search  # ty: ignore[invalid-assignment]

    with pytest.raises(HTTPException, match="rate limit exceeded"):
        client.test_connection()
