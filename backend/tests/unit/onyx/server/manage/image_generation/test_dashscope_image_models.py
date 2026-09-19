"""Tests for the Bailian (DashScope) image model listing endpoint.

Verifies that the workspace's model listing is filtered to the qwen-image
family, merged with the known-model seed list, and that each entry carries
the supported parameters from the generation-and-editing API.
"""

from typing import cast
from unittest.mock import patch

from sqlalchemy.orm import Session

from onyx.db.models import User
from onyx.server.manage.image_generation.api import (
    get_dashscope_available_image_models,
)
from onyx.server.manage.image_generation.models import DashscopeImageModelsRequest

_SAMPLE = {
    "object": "list",
    "data": [
        {"id": "qwen3.8-max"},  # chat model - ignored here
        {"id": "qwen-image-3.0-pro"},
        {"id": "qwen-image-3.0"},
        {"id": "text-embedding-v4"},
    ],
}


def _fetch(sample: dict = _SAMPLE) -> dict:
    with (
        patch(
            "onyx.server.manage.image_generation.api._resolve_api_key",
            return_value="sk-key",
        ),
        patch(
            "onyx.server.manage.image_generation.api._get_openai_compatible_models_response",
            return_value=sample,
        ) as mock_response,
    ):
        results = get_dashscope_available_image_models(
            request=DashscopeImageModelsRequest(
                api_key="sk-key",
                api_base="https://ws1.cn-beijing.maas.aliyuncs.com",
            ),
            _=cast(User, None),
            db_session=cast(Session, None),
        )
    assert mock_response.call_args.kwargs["url"] == (
        "https://ws1.cn-beijing.maas.aliyuncs.com/compatible-mode/v1/models"
    )
    return {r.name: r for r in results}


def test_fetched_image_models_kept_and_chat_models_ignored() -> None:
    by_name = _fetch()
    assert "qwen-image-3.0-pro" in by_name
    assert "qwen-image-3.0" in by_name
    assert "qwen3.8-max" not in by_name
    assert "text-embedding-v4" not in by_name


def test_seed_models_merged_when_not_fetched() -> None:
    # The models listing has no image models at all; the seed family fills in.
    by_name = _fetch(sample={"object": "list", "data": [{"id": "qwen3.8-max"}]})
    assert "qwen-image-3.0" in by_name
    assert "qwen-image-edit" in by_name


def test_models_carry_supported_parameters() -> None:
    by_name = _fetch()
    model = by_name["qwen-image-3.0"]
    assert model.default_size == "1024x1024"
    assert model.size_range == "512x512-2048x2048"
    assert model.max_images_per_request == 6
    assert model.supports_reference_images is True
    assert model.max_reference_images == 3
    assert model.watermark is False
    assert model.prompt_extend is True


def test_recommended_default_flag() -> None:
    by_name = _fetch()
    assert by_name["qwen-image-3.0"].is_recommended_default is True
    assert by_name["qwen-image-3.0-pro"].is_recommended_default is False
