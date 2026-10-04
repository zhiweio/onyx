import requests
from fastapi import HTTPException

from onyx.tools.tool_implementations.web_search.models import (
    WebSearchProvider,
    WebSearchResult,
)
from onyx.utils.logger import setup_logger
from onyx.utils.retry_wrapper import retry_builder

logger = setup_logger()

BAIDU_SEARCH_URL = "https://openapi.baidu.com/rest/2.0/search"
BAIDU_REQUEST_TIMEOUT_SECONDS = 15


class BaiduClient(WebSearchProvider):
    """Baidu search open API (JSON) — https://openapi.baidu.com."""

    def __init__(self, api_key: str, num_results: int = 10) -> None:
        # Baidu's open API authenticates with the access_token query parameter.
        self._access_token = api_key
        self._num_results = num_results

    @retry_builder(tries=3, delay=1, backoff=2)
    def search(self, query: str) -> list[WebSearchResult]:
        response = requests.get(
            BAIDU_SEARCH_URL,
            params={
                "access_token": self._access_token,
                "q": query,
                "num": self._num_results,
            },
            timeout=BAIDU_REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()

        results = response.json().get("results") or []
        validated_results: list[WebSearchResult] = []
        for item in results:
            link = (item.get("url") or item.get("link") or "").strip()
            if not link:
                continue
            validated_results.append(
                WebSearchResult(
                    title=(item.get("title") or "").strip(),
                    link=link,
                    snippet=(item.get("abstract") or "").strip(),
                )
            )
        return validated_results

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
                "token" in error_msg.lower()
                or "auth" in error_msg.lower()
                or "401" in error_msg
            ):
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid Baidu access token: {error_msg}",
                ) from e
            raise HTTPException(
                status_code=400,
                detail=f"Baidu API key validation failed: {error_msg}",
            ) from e

        logger.info("Web search provider test succeeded for Baidu.")
        return {"status": "ok"}
