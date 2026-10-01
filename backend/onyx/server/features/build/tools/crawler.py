"""Crawler platform client: async submit → poll extracted content.

Works with any crawler service exposing the two-call contract
(Crawl4AI server, or the enterprise crawler platform):

- ``POST {base}/crawl`` {url} → {job_id}
- ``GET {base}/crawl/{job_id}`` → {status, content|error}

``CRAWLER_BASE_URL`` configures the endpoint; empty disables the tool.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

import requests

from onyx.utils.logger import setup_logger

logger = setup_logger()

CRAWLER_BASE_ENV = "CRAWLER_BASE_URL"
DEFAULT_POLL_INTERVAL_SECONDS = 2.0
DEFAULT_MAX_WAIT_SECONDS = 60.0


class CrawlerError(Exception):
    """Crawler refused the job or the wait timed out."""


@dataclass(frozen=True)
class CrawlResult:
    url: str
    status: str
    content: str = ""
    error: str | None = None

    @property
    def done(self) -> bool:
        return self.status in ("done", "completed", "failed", "error")


class CrawlerClient:
    def __init__(
        self,
        base_url: str,
        *,
        api_key: str | None = None,
        poll_interval: float = DEFAULT_POLL_INTERVAL_SECONDS,
        max_wait: float = DEFAULT_MAX_WAIT_SECONDS,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._session = requests.Session()
        if api_key:
            self._session.headers["Authorization"] = f"Bearer {api_key}"
        self._poll_interval = poll_interval
        self._max_wait = max_wait

    def submit(self, url: str) -> str:
        resp = self._session.post(f"{self._base}/crawl", json={"url": url}, timeout=30)
        if resp.status_code != 200:
            raise CrawlerError(f"submit failed: HTTP {resp.status_code}")
        data: dict[str, Any] = resp.json()
        job_id = data.get("job_id") or data.get("id")
        if not job_id:
            raise CrawlerError(f"crawler returned no job id: {data}")
        return str(job_id)

    def poll(self, job_id: str) -> CrawlResult:
        resp = self._session.get(f"{self._base}/crawl/{job_id}", timeout=30)
        if resp.status_code != 200:
            raise CrawlerError(f"poll failed: HTTP {resp.status_code}")
        data: dict[str, Any] = resp.json()
        return CrawlResult(
            url=str(data.get("url") or ""),
            status=str(data.get("status") or "unknown"),
            content=str(data.get("content") or data.get("markdown") or ""),
            error=(str(data["error"]) if data.get("error") else None),
        )

    def crawl_sync(self, url: str) -> CrawlResult:
        """Submit and wait (bounded) for the extracted content."""
        job_id = self.submit(url)
        deadline = time.time() + self._max_wait
        while time.time() < deadline:
            result = self.poll(job_id)
            if result.done:
                return result
            time.sleep(self._poll_interval)
        raise CrawlerError(f"crawl of {url} did not finish in {self._max_wait}s")


def build_crawler_client() -> CrawlerClient | None:
    """The configured crawler, or None when unconfigured."""
    base = os.environ.get(CRAWLER_BASE_ENV, "").strip()
    if not base:
        return None
    return CrawlerClient(base, api_key=os.environ.get("CRAWLER_API_KEY") or None)
