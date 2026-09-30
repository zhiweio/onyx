"""Tests for the DashScope (Alibaba Bailian) model fetcher.

Verifies the mapping from a Bailian workspace's OpenAI-shaped /v1/models
response to Onyx model configs: non-chat models (image, video, embedding)
dropped, metadata pulled from the LiteLLM cost map, and results sorted by
name.
"""

from typing import cast
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from onyx.error_handling.exceptions import OnyxError
from onyx.db.models import User
from onyx.server.manage.llm.api import (
    _get_dashscope_models_url,
    get_dashscope_available_models,
)
from onyx.server.manage.llm.models import DashscopeModelsRequest

# Trimmed /v1/models payload: chat models, a vision-chat model, and several
# non-chat entries that must be dropped.
_SAMPLE = {
    "object": "list",
    "data": [
        {"id": "qwen3.8-max"},
        {"id": "qwen3.8-flash"},
        {"id": "qwen3-vl-plus"},
        {"id": "qwen-image-3.0"},
        {"id": "wan2.2-t2v-turbo"},
        {"id": "text-embedding-v4"},
        {"id": "cosyvoice-v3"},
        {"id": ""},
    ],
}


def _fetch(api_base: str = "https://ws1.cn-beijing.maas.aliyuncs.com") -> dict:
    with (
        patch(
            "onyx.server.manage.llm.api._resolve_api_key",
            return_value="sk-key",
        ),
        patch(
            "onyx.server.manage.llm.api._get_openai_compatible_models_response",
            return_value=_SAMPLE,
        ) as mock_response,
    ):
        results = get_dashscope_available_models(
            request=DashscopeModelsRequest(
                api_base=api_base,
                api_key="sk-key",
                provider_id=None,  # skip DB sync
            ),
            _=cast(User, None),
            db_session=cast(Session, None),
        )
    # The workspace domain is normalized to the compatible-mode models URL.
    assert mock_response.call_args.kwargs["url"] == (
        "https://ws1.cn-beijing.maas.aliyuncs.com/compatible-mode/v1/models"
    )
    return {r.name: r for r in results}


def test_non_chat_models_dropped() -> None:
    by_name = _fetch()
    assert set(by_name) == {"qwen3.8-max", "qwen3.8-flash", "qwen3-vl-plus"}


def test_metadata_from_litellm_cost_map() -> None:
    by_name = _fetch()
    # qwen3.8-max: ~1M context in the LiteLLM cost map.
    assert by_name["qwen3.8-max"].max_input_tokens is not None
    assert by_name["qwen3.8-max"].max_input_tokens > 900_000
    assert by_name["qwen3.8-max"].supports_reasoning is True
    # qwen3-vl-plus is a vision model.
    assert by_name["qwen3-vl-plus"].supports_image_input is True


def test_display_name_falls_back_to_id() -> None:
    by_name = _fetch()
    assert by_name["qwen3.8-max"].display_name == "qwen3.8-max"


def test_results_sorted_by_name() -> None:
    by_name = _fetch()
    assert list(by_name) == sorted(by_name, key=str.lower)


def test_only_non_chat_models_raises() -> None:
    with (
        patch(
            "onyx.server.manage.llm.api._resolve_api_key",
            return_value="sk-key",
        ),
        patch(
            "onyx.server.manage.llm.api._get_openai_compatible_models_response",
            return_value={"data": [{"id": "qwen-image-3.0"}, {"id": "wanx2.1-t2i-turbo"}]},
        ),
    ):
        with pytest.raises(OnyxError):
            get_dashscope_available_models(
                request=DashscopeModelsRequest(api_base="https://x.maas.aliyuncs.com"),
                _=cast(User, None),
                db_session=cast(Session, None),
            )


def test_models_url_accepts_all_base_shapes() -> None:
    expected = "https://ws1.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1/models"
    assert _get_dashscope_models_url("https://ws1.ap-southeast-1.maas.aliyuncs.com") == (
        expected
    )
    assert (
        _get_dashscope_models_url(
            "https://ws1.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1"
        )
        == expected
    )
    assert (
        _get_dashscope_models_url(
            "https://ws1.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1/"
        )
        == expected
    )
