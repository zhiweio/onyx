import requests
from fastapi import HTTPException

from onyx.tools.tool_implementations.web_search.models import (
    WebSearchProvider,
    WebSearchResult,
)
from onyx.utils.logger import setup_logger
from onyx.utils.retry_wrapper import retry_builder

logger = setup_logger()

BOCHA_SEARCH_URL = "https://open.bochaai.com/v1/web-search"
BOCHA_REQUEST_TIMEOUT_SECONDS = 15


class BochaClient(WebSearchProvider):
    """Bocha (博查) web search API — https://open.bochaai.com."""

    def __init__(self, api_key: str, num_results: int = 10) -> None:
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        self._num_results = num_results

    @retry_builder(tries=3, delay=1, backoff=2)
    def search(self, query: str) -> list[WebSearchResult]:
        response = requests.post(
            BOCHA_SEARCH_URL,
            headers=self._headers,
            json={"query": query, "count": self._num_results, "summary": True},
            timeout=BOCHA_REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()

        web_pages = (response.json().get("data") or {}).get("webPages") or []
        results: list[WebSearchResult] = []
        for item in web_pages:
            link = (item.get("url") or "").strip()
            if not link:
                continue
            results.append(
                WebSearchResult(
                    title=(item.get("name") or "").strip(),
                    link=link,
                    snippet=(item.get("summary") or item.get("snippet") or "").strip(),
                )
            )
        return results

    def test_connection(self) -> dict[str, str]:
        try:
            test_results = self.search("test")
            if not test_results or not any(result.link for result in test_results):
                raise HTTPException(
                    status_code=400,
                    detail="API key validation failed: search returned no results.",
                )
        except HTTPException:
            raise
        except Exception as e:
            error_msg = str(e)
            if (
                "api" in error_msg.lower()
                or "key" in error_msg.lower()
                or "auth" in error_msg.lower()
                or "401" in error_msg
            ):
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid Bocha API key: {error_msg}",
                ) from e
            raise HTTPException(
                status_code=400,
                detail=f"Bocha API key validation failed: {error_msg}",
            ) from e

        logger.info("Web search provider test succeeded for Bocha.")
        return {"status": "ok"}
