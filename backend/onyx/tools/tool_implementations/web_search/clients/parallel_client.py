from __future__ import annotations

import parallel
from fastapi import HTTPException
from parallel import Parallel

from onyx.connectors.cross_connector_utils.miscellaneous_utils import time_str_to_utc
from onyx.tools.tool_implementations.web_search.models import (
    WebSearchProvider,
    WebSearchResult,
)
from onyx.utils.logger import setup_logger

logger = setup_logger()

PARALLEL_REQUEST_TIMEOUT_SECONDS = 60.0
PARALLEL_MAX_OBJECTIVE_CHARS = 5000
PARALLEL_MAX_SEARCH_QUERY_CHARS = 200


class ParallelClient(WebSearchProvider):
    def __init__(self, api_key: str, num_results: int = 10) -> None:
        self._client = Parallel(
            api_key=api_key,
            timeout=PARALLEL_REQUEST_TIMEOUT_SECONDS,
        )
        self._num_results = max(1, num_results)

    def search(self, query: str) -> list[WebSearchResult]:
        objective = query.strip()[:PARALLEL_MAX_OBJECTIVE_CHARS]
        search_query = query.strip()[:PARALLEL_MAX_SEARCH_QUERY_CHARS]
        if not search_query:
            raise ValueError("Parallel search query must not be empty.")

        response = self._client.search(
            objective=objective,
            search_queries=[search_query],
            mode="fast",
            advanced_settings={"max_results": self._num_results},
        )

        results: list[WebSearchResult] = []
        for result in response.results:
            link = (result.url or "").strip()
            if not link:
                continue

            excerpts = result.excerpts or []
            snippet = "\n".join(
                excerpt.strip() for excerpt in excerpts if excerpt and excerpt.strip()
            )
            published_date = None
            if result.publish_date:
                published_date = time_str_to_utc(result.publish_date)

            results.append(
                WebSearchResult(
                    title=(result.title or "").strip(),
                    link=link,
                    snippet=snippet,
                    author=None,
                    published_date=published_date,
                )
            )

        return results

    def test_connection(self) -> dict[str, str]:
        try:
            test_results = self.search("test")
            if not test_results or not any(result.link for result in test_results):
                raise HTTPException(
                    status_code=400,
                    detail="Parallel API key validation failed: search returned no results.",
                )
        except HTTPException:
            raise
        except parallel.AuthenticationError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid Parallel API key: {exc}",
            ) from exc
        except parallel.RateLimitError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Parallel API rate limit exceeded: {exc}",
            ) from exc
        except (ValueError, parallel.APIStatusError) as exc:
            error_msg = str(exc)
            lower = error_msg.lower()
            if "401" in lower or "403" in lower or "api key" in lower or "auth" in lower:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid Parallel API key: {error_msg}",
                ) from exc
            if "429" in lower or "rate limit" in lower:
                raise HTTPException(
                    status_code=400,
                    detail=f"Parallel API rate limit exceeded: {error_msg}",
                ) from exc
            raise HTTPException(
                status_code=400,
                detail=f"Parallel API key validation failed: {error_msg}",
            ) from exc

        logger.info("Web search provider test succeeded for Parallel.")
        return {"status": "ok"}
