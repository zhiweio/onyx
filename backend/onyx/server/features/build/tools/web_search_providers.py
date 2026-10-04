"""Pluggable web search providers (Bocha / Baidu / SearXNG).

The web_search tool resolves its provider like chat's web search: the
active provider row configured in the admin panel is the source of truth
(``build_configured_search_provider``), and the env channel below is the
fallback for deployments without an admin row.

Env channel — one interface, three mainland-relevant implementations:

- Bocha (博查) — commercial Chinese web search API
- Baidu search open API
- SearXNG — self-hosted metasearch (no key, fully private; popular for
  intranet deployments)

Selected by ``WEB_SEARCH_PROVIDER`` (bocha | baidu | searxng) with the
API key from the matching env var. All return the same hit shape so the
web_search tool stays provider-agnostic.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Protocol

import requests

from onyx.utils.logger import setup_logger

logger = setup_logger()

PROVIDER_ENV = "WEB_SEARCH_PROVIDER"


@dataclass(frozen=True)
class WebSearchHit:
    title: str
    url: str
    snippet: str
    published: str | None = None


class WebSearchProvider(Protocol):
    name: str

    def search(self, query: str, max_results: int = 8) -> list[WebSearchHit]: ...


def _truncate(text: str, limit: int = 400) -> str:
    return text if len(text) <= limit else text[:limit] + "…"


class BochaSearchProvider:
    """https://open.bochaai.com — POST web-search with a Bearer key."""

    name = "bocha"
    ENDPOINT = "https://api.bochaai.com/v1/web-search"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def search(self, query: str, max_results: int = 8) -> list[WebSearchHit]:
        resp = requests.post(
            self.ENDPOINT,
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={"query": query, "count": max_results, "summary": True},
            timeout=15,
        )
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        hits = [
            WebSearchHit(
                title=str(item.get("name") or item.get("url") or ""),
                url=str(item.get("url") or ""),
                snippet=_truncate(
                    str(item.get("summary") or item.get("snippet") or "")
                ),
            )
            for item in (data.get("data") or {}).get("webPages") or []
        ]
        return hits[:max_results]


class BaiduSearchProvider:
    """Baidu search open API (JSON)."""

    name = "baidu"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def search(self, query: str, max_results: int = 8) -> list[WebSearchHit]:
        resp = requests.get(
            "https://openapi.baidu.com/rest/2.0/search",
            params={"access_token": self._api_key, "q": query, "num": max_results},
            timeout=15,
        )
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        hits = [
            WebSearchHit(
                title=str(item.get("title") or ""),
                url=str(item.get("url") or item.get("link") or ""),
                snippet=_truncate(str(item.get("abstract") or "")),
            )
            for item in data.get("results") or []
        ]
        return hits[:max_results]


class SearXNGSearchProvider:
    """Self-hosted SearXNG JSON API (format=json must be enabled)."""

    name = "searxng"

    def __init__(self, base_url: str) -> None:
        self._base_url = base_url.rstrip("/")

    def search(self, query: str, max_results: int = 8) -> list[WebSearchHit]:
        resp = requests.get(
            f"{self._base_url}/search",
            params={"q": query, "format": "json"},
            timeout=15,
        )
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        hits = [
            WebSearchHit(
                title=str(item.get("title") or item.get("url") or ""),
                url=str(item.get("url") or ""),
                snippet=_truncate(str(item.get("content") or "")),
                published=str(item.get("publishedDate") or "") or None,
            )
            for item in data.get("results") or []
        ]
        return hits[:max_results]


def build_search_provider(
    provider_name: str | None = None,
    *,
    bocha_key: str | None = None,
    baidu_key: str | None = None,
    searxng_url: str | None = None,
) -> WebSearchProvider | None:
    """Construct the configured provider; None when unconfigured."""
    name = (provider_name or os.environ.get(PROVIDER_ENV, "")).strip().lower()
    if not name:
        return None
    if name == "bocha":
        key = bocha_key or os.environ.get("BOCHA_API_KEY", "")
        return BochaSearchProvider(key) if key else None
    if name == "baidu":
        key = baidu_key or os.environ.get("BAIDU_SEARCH_API_KEY", "")
        return BaiduSearchProvider(key) if key else None
    if name == "searxng":
        url = searxng_url or os.environ.get("SEARXNG_BASE_URL", "")
        return SearXNGSearchProvider(url) if url else None
    logger.warning("unknown WEB_SEARCH_PROVIDER %r", name)
    return None


def build_configured_search_provider() -> WebSearchProvider | None:
    """The chat-configured admin search provider, with the env fallback.

    The active provider row configured in the admin panel is the source
    of truth — the same row chat's web search uses, so one admin setting
    covers chat and craft. Deployments without an admin row keep the
    env-channel provider. A broken row logs a warning and falls back
    instead of raising — this runs inside the tool-bridge registry build.
    """
    from onyx.db.engine.sql_engine import get_session_with_current_tenant
    from onyx.db.web_search import fetch_active_web_search_provider
    from onyx.tools.tool_implementations.web_search.providers import (
        build_search_provider_from_config,
    )
    from shared_configs.enums import WebSearchProviderType

    with get_session_with_current_tenant() as db_session:
        provider_model = fetch_active_web_search_provider(db_session)

    if provider_model is not None:
        try:
            provider = build_search_provider_from_config(
                provider_type=WebSearchProviderType(provider_model.provider_type),
                api_key=(
                    provider_model.api_key.get_value(apply_mask=False)
                    if provider_model.api_key
                    else None
                ),
                config=provider_model.config or {},
            )
        except ValueError as exc:
            logger.warning(
                "Active web search provider '%s' is misconfigured (%s); "
                "falling back to the env channel",
                provider_model.name,
                exc,
            )
        else:
            return AdminSearchProvider(provider_model.provider_type, provider)
    return build_search_provider()


class AdminSearchProvider:
    """Adapts a chat-side search provider to the craft tool interface."""

    def __init__(self, name: str, provider: Any) -> None:
        self.name = name
        self._provider = provider

    def search(self, query: str, max_results: int = 8) -> list[WebSearchHit]:
        results = list(self._provider.search(query))[:max_results]
        return [
            WebSearchHit(
                title=result.title,
                url=result.link,
                snippet=_truncate(result.snippet),
                published=(
                    result.published_date.date().isoformat()
                    if result.published_date
                    else None
                ),
            )
            for result in results
        ]


def format_hits(query: str, hits: list[WebSearchHit]) -> str:
    if not hits:
        return f"[web_search] no results for {query!r}"
    lines = [f"Web search results for {query!r}:"]
    for i, hit in enumerate(hits, start=1):
        line = f"{i}. {hit.title} — {hit.url}"
        if hit.published:
            line += f" (published {hit.published})"
        if hit.snippet:
            line += f"\n   {hit.snippet}"
        lines.append(line)
    return "\n\n".join(lines)
