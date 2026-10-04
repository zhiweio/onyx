from types import SimpleNamespace
from unittest.mock import patch

import pytest

import onyx.tools.tool_implementations.web_search.clients.baidu_client as baidu_client_module
import onyx.tools.tool_implementations.web_search.clients.bocha_client as bocha_client_module
from onyx.tools.tool_implementations.web_search.clients.baidu_client import BaiduClient
from onyx.tools.tool_implementations.web_search.clients.bocha_client import BochaClient
from onyx.tools.tool_implementations.web_search.clients.brave_client import BraveClient
from onyx.tools.tool_implementations.web_search.clients.parallel_client import (
    ParallelClient,
)
from onyx.tools.tool_implementations.web_search.providers import (
    build_search_provider_from_config,
    provider_requires_api_key,
)
from shared_configs.enums import WebSearchProviderType


def test_provider_requires_api_key() -> None:
    """Test that provider_requires_api_key correctly identifies which providers need API keys."""
    assert provider_requires_api_key(WebSearchProviderType.EXA) is True
    assert provider_requires_api_key(WebSearchProviderType.BRAVE) is True
    assert provider_requires_api_key(WebSearchProviderType.SERPER) is True
    assert provider_requires_api_key(WebSearchProviderType.GOOGLE_PSE) is True
    assert provider_requires_api_key(WebSearchProviderType.PARALLEL) is True
    assert provider_requires_api_key(WebSearchProviderType.SEARXNG) is False


def test_build_searxng_provider_without_api_key() -> None:
    """Test that SearXNG provider can be built without an API key."""
    provider = build_search_provider_from_config(
        provider_type=WebSearchProviderType.SEARXNG,
        api_key=None,
        config={"searxng_base_url": "http://localhost:8080"},
    )
    assert provider is not None


def test_build_searxng_provider_requires_base_url() -> None:
    """Test that SearXNG provider requires a base URL."""
    with pytest.raises(ValueError, match="Please provide a URL"):
        build_search_provider_from_config(
            provider_type=WebSearchProviderType.SEARXNG,
            api_key=None,
            config={},
        )


def test_build_exa_provider_requires_api_key() -> None:
    """Test that Exa provider requires an API key."""
    with pytest.raises(ValueError, match="API key is required"):
        build_search_provider_from_config(
            provider_type=WebSearchProviderType.EXA,
            api_key=None,
            config={},
        )


def test_build_brave_provider_requires_api_key() -> None:
    """Test that Brave provider requires an API key."""
    with pytest.raises(ValueError, match="API key is required"):
        build_search_provider_from_config(
            provider_type=WebSearchProviderType.BRAVE,
            api_key=None,
            config={},
        )


def test_build_brave_provider_with_optional_config() -> None:
    provider = build_search_provider_from_config(
        provider_type=WebSearchProviderType.BRAVE,
        api_key="test-api-key",
        config={
            "country": "us",
            "search_lang": "en",
            "ui_lang": "en-US",
            "safesearch": "strict",
            "freshness": "pm",
            "timeout_seconds": "12",
        },
    )
    assert isinstance(provider, BraveClient)
    assert provider._country == "US"  # noqa: SLF001
    assert provider._search_lang == "en"  # noqa: SLF001
    assert provider._ui_lang == "en-US"  # noqa: SLF001
    assert provider._safesearch == "strict"  # noqa: SLF001
    assert provider._freshness == "pm"  # noqa: SLF001
    assert provider._timeout_seconds == 12  # noqa: SLF001


def test_build_brave_provider_rejects_invalid_timeout() -> None:
    with pytest.raises(ValueError, match="timeout_seconds"):
        build_search_provider_from_config(
            provider_type=WebSearchProviderType.BRAVE,
            api_key="test-api-key",
            config={"timeout_seconds": "not-an-int"},
        )


def test_build_serper_provider_requires_api_key() -> None:
    """Test that Serper provider requires an API key."""
    with pytest.raises(ValueError, match="API key is required"):
        build_search_provider_from_config(
            provider_type=WebSearchProviderType.SERPER,
            api_key=None,
            config={},
        )


def test_build_google_pse_provider_requires_api_key() -> None:
    """Test that Google PSE provider requires an API key."""
    with pytest.raises(ValueError, match="API key is required"):
        build_search_provider_from_config(
            provider_type=WebSearchProviderType.GOOGLE_PSE,
            api_key=None,
            config={"search_engine_id": "test-cx"},
        )


def test_build_parallel_provider_requires_api_key() -> None:
    """Test that Parallel provider requires an API key."""
    with pytest.raises(ValueError, match="API key is required"):
        build_search_provider_from_config(
            provider_type=WebSearchProviderType.PARALLEL,
            api_key=None,
            config={},
        )


def test_build_parallel_provider() -> None:
    provider = build_search_provider_from_config(
        provider_type=WebSearchProviderType.PARALLEL,
        api_key="test-api-key",
        config={},
    )
    assert isinstance(provider, ParallelClient)


def test_build_google_pse_provider_requires_search_engine_id() -> None:
    """Test that Google PSE provider requires a search engine ID."""
    with pytest.raises(ValueError, match="search engine id"):
        build_search_provider_from_config(
            provider_type=WebSearchProviderType.GOOGLE_PSE,
            api_key="test-api-key",
            config={},
        )


def test_provider_requires_api_key_bocha_baidu() -> None:
    assert provider_requires_api_key(WebSearchProviderType.BOCHA) is True
    assert provider_requires_api_key(WebSearchProviderType.BAIDU) is True


def test_build_bocha_provider_requires_api_key() -> None:
    with pytest.raises(ValueError, match="API key is required"):
        build_search_provider_from_config(
            provider_type=WebSearchProviderType.BOCHA,
            api_key=None,
            config={},
        )


def test_build_bocha_provider() -> None:
    provider = build_search_provider_from_config(
        provider_type=WebSearchProviderType.BOCHA,
        api_key="test-api-key",
        config={},
    )
    assert isinstance(provider, BochaClient)


def test_build_baidu_provider_requires_api_key() -> None:
    with pytest.raises(ValueError, match="API key is required"):
        build_search_provider_from_config(
            provider_type=WebSearchProviderType.BAIDU,
            api_key=None,
            config={},
        )


def test_build_baidu_provider() -> None:
    provider = build_search_provider_from_config(
        provider_type=WebSearchProviderType.BAIDU,
        api_key="test-access-token",
        config={},
    )
    assert isinstance(provider, BaiduClient)


def test_bocha_client_parses_web_pages() -> None:
    client = BochaClient(api_key="test-api-key", num_results=5)
    payload = {
        "data": {
            "webPages": [
                {
                    "name": "增值税法全文",
                    "url": "https://www.gov.cn/yaowen/liebiao/vat-law",
                    "summary": "2026年1月1日起施行。",
                },
                {"name": "无链接条目", "url": "", "summary": "应被跳过"},
            ]
        }
    }
    with patch.object(
        bocha_client_module.requests, "post", return_value=_fake_response(payload)
    ):
        results = client.search("增值税法")
    assert len(results) == 1
    assert results[0].title == "增值税法全文"
    assert results[0].link == "https://www.gov.cn/yaowen/liebiao/vat-law"
    assert "2026年1月1日" in results[0].snippet


def test_baidu_client_parses_results() -> None:
    client = BaiduClient(api_key="test-access-token", num_results=5)
    payload = {
        "results": [
            {
                "title": "雪龙集团最新公告",
                "url": "https://www.cninfo.com.cn/xuelong",
                "abstract": "雪龙集团公告摘要。",
            },
            {"title": "仅链接字段", "link": "https://example.com/link-only"},
        ]
    }
    with patch.object(
        baidu_client_module.requests, "get", return_value=_fake_response(payload)
    ):
        results = client.search("雪龙集团")
    assert len(results) == 2
    assert results[0].link == "https://www.cninfo.com.cn/xuelong"
    assert results[1].link == "https://example.com/link-only"
    assert results[1].snippet == ""


def _fake_response(payload: dict) -> SimpleNamespace:
    response = SimpleNamespace(
        status_code=200,
        payload=payload,
        raise_for_status=lambda: None,
    )
    response.json = lambda: payload  # type: ignore[method-assign]
    return response
