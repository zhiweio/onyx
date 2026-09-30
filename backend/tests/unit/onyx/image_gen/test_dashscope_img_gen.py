"""Tests for the DashScope (Bailian) image generation provider.

Verifies credential building, workspace-domain normalization, request shaping
for text-to-image and image-to-image calls, URL-to-b64 result conversion, and
error mapping — all with httpx mocked.
"""

import base64
from typing import cast
from unittest.mock import patch

import httpx
import pytest

from onyx.image_gen.exceptions import ImageProviderCredentialsError
from onyx.image_gen.factory import get_image_generation_provider
from onyx.image_gen.interfaces import ImageGenerationProviderCredentials, ReferenceImage
from onyx.image_gen.providers.dashscope_img_gen import (
    DashScopeImageGenerationProvider,
)

DASHSCOPE_PROVIDER = "dashscope"
WORKSPACE_BASE = "https://ws1.cn-beijing.maas.aliyuncs.com"


def _success_response(image_url: str = "https://result.example.com/img.png") -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "output": {
                "choices": [
                    {"message": {"content": [{"image": image_url}]}}
                ]
            },
            "usage": {"image_count": 1},
            "request_id": "req-1",
        },
    )


def _download_response(content: bytes = b"png-bytes") -> httpx.Response:
    return httpx.Response(200, content=content)


def test_build_provider_from_credentials() -> None:
    credentials = ImageGenerationProviderCredentials(
        api_key="sk-test",
        api_base=f"{WORKSPACE_BASE}/compatible-mode/v1",
    )

    provider = get_image_generation_provider(DASHSCOPE_PROVIDER, credentials)

    assert isinstance(provider, DashScopeImageGenerationProvider)
    # The compatible-mode suffix is stripped down to the bare workspace domain.
    assert provider._api_base == WORKSPACE_BASE
    assert provider.supports_reference_images is True
    assert provider.max_reference_images == 3


def test_build_provider_requires_key_and_base() -> None:
    for missing in ("api_key", "api_base"):
        credentials = ImageGenerationProviderCredentials(
            api_key="sk-test", api_base=WORKSPACE_BASE
        )
        setattr(credentials, missing, None)

        assert DashScopeImageGenerationProvider.validate_credentials(credentials) is False
        with pytest.raises(ImageProviderCredentialsError):
            get_image_generation_provider(DASHSCOPE_PROVIDER, credentials)


def test_generate_image_text_to_image_request_shape() -> None:
    provider = DashScopeImageGenerationProvider(
        api_key="sk-test", api_base=WORKSPACE_BASE
    )

    with (
        patch("httpx.post", return_value=_success_response()) as mock_post,
        patch("httpx.get", return_value=_download_response(b"img-data")) as mock_get,
    ):
        response = provider.generate_image(
            prompt="a mountain at sunset",
            model="qwen-image-3.0",
            size="1024x1536",
            n=1,
        )

    # Endpoint, auth header and multimodal-generation payload shape.
    assert mock_post.call_args.args[0] == (
        f"{WORKSPACE_BASE}/api/v1/services/aigc/multimodal-generation/generation"
    )
    assert mock_post.call_args.kwargs["headers"]["Authorization"] == "Bearer sk-test"
    payload = mock_post.call_args.kwargs["json"]
    assert payload["model"] == "qwen-image-3.0"
    content = payload["input"]["messages"][0]["content"]
    assert content == [{"text": "a mountain at sunset"}]
    # size separator converted, n omitted at 1 (API default).
    assert payload["parameters"] == {"size": "1024*1536"}

    # Result URL downloaded and inlined as base64.
    assert mock_get.call_args.args[0] == "https://result.example.com/img.png"
    assert response.data[0].b64_json == base64.b64encode(b"img-data").decode()
    assert response.data[0].revised_prompt == "a mountain at sunset"


def test_generate_image_with_reference_images() -> None:
    provider = DashScopeImageGenerationProvider(
        api_key="sk-test", api_base=WORKSPACE_BASE
    )
    reference_images = [
        ReferenceImage(data=b"img-1", mime_type="image/png"),
        ReferenceImage(data=b"img-2", mime_type="image/jpeg"),
    ]

    with (
        patch("httpx.post", return_value=_success_response()) as mock_post,
        patch("httpx.get", return_value=_download_response()),
    ):
        provider.generate_image(
            prompt="make this watercolor",
            model="qwen-image-3.0",
            size="1024x1024",
            n=2,
            reference_images=reference_images,
        )

    payload = mock_post.call_args.kwargs["json"]
    content = payload["input"]["messages"][0]["content"]
    # Reference images become data-URL entries ahead of the prompt.
    assert content[0] == {"image": "data:image/png;base64," + base64.b64encode(b"img-1").decode()}
    assert content[1] == {"image": "data:image/jpeg;base64," + base64.b64encode(b"img-2").decode()}
    assert content[2] == {"text": "make this watercolor"}
    # n>1 is sent explicitly.
    assert payload["parameters"]["n"] == 2


def test_generate_image_rejects_too_many_reference_images() -> None:
    provider = DashScopeImageGenerationProvider(
        api_key="sk-test", api_base=WORKSPACE_BASE
    )
    reference_images = [
        ReferenceImage(data=b"img", mime_type="image/png") for _ in range(4)
    ]

    with pytest.raises(ValueError):
        provider.generate_image(
            prompt="edit",
            model="qwen-image-3.0",
            size="1024x1024",
            n=1,
            reference_images=reference_images,
        )


def test_generate_image_maps_error_body() -> None:
    provider = DashScopeImageGenerationProvider(
        api_key="sk-test", api_base=WORKSPACE_BASE
    )
    error_response = httpx.Response(
        200,
        json={"code": "InvalidParameter", "message": "size not supported", "request_id": "req-2"},
    )

    with (
        patch("httpx.post", return_value=error_response),
        patch("httpx.get") as mock_get,
    ):
        with pytest.raises(RuntimeError) as exc_info:
            provider.generate_image(
                prompt="a cat",
                model="qwen-image-3.0",
                size="1024x1024",
                n=1,
            )

    assert "size not supported" in str(exc_info.value)
    mock_get.assert_not_called()


def test_generate_image_maps_http_error() -> None:
    provider = DashScopeImageGenerationProvider(
        api_key="sk-test", api_base=WORKSPACE_BASE
    )

    with (
        patch(
            "httpx.post",
            return_value=httpx.Response(
                401, json={"code": "InvalidApiKey", "message": "Invalid API key"}
            ),
        ),
    ):
        with pytest.raises(RuntimeError) as exc_info:
            provider.generate_image(
                prompt="a cat",
                model="qwen-image-3.0",
                size="1024x1024",
                n=1,
            )

    assert "401" in str(exc_info.value)
    assert "Invalid API key" in str(exc_info.value)


def test_generate_image_strips_provider_prefix_from_model() -> None:
    provider = DashScopeImageGenerationProvider(
        api_key="sk-test", api_base=WORKSPACE_BASE
    )

    with (
        patch("httpx.post", return_value=_success_response()) as mock_post,
        patch("httpx.get", return_value=_download_response()),
    ):
        provider.generate_image(
            prompt="a cat",
            model="dashscope/qwen-image-3.0",
            size="1024x1024",
            n=1,
        )

    assert mock_post.call_args.kwargs["json"]["model"] == "qwen-image-3.0"
