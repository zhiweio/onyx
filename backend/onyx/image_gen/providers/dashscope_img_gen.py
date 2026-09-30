from __future__ import annotations

import base64
from datetime import datetime
from typing import TYPE_CHECKING, Any

import httpx

from onyx.image_gen.exceptions import ImageProviderCredentialsError
from onyx.image_gen.interfaces import (
    ImageGenerationProvider,
    ImageGenerationProviderCredentials,
    ReferenceImage,
)
from onyx.tracing.flows import LLMFlow
from onyx.tracing.llm_utils import traced_llm_call

if TYPE_CHECKING:
    from onyx.image_gen.interfaces import ImageGenerationResponse


# Synchronous text-to-image / image-to-image endpoint shared by the qwen-image
# family on Alibaba Bailian (Model Studio).
_IMAGE_GENERATION_PATH = "/api/v1/services/aigc/multimodal-generation/generation"

# The qwen-image generation-and-editing API accepts at most 3 reference images.
_MAX_REFERENCE_IMAGES = 3

_GENERATION_TIMEOUT_SECONDS = 300.0
_DOWNLOAD_TIMEOUT_SECONDS = 60.0

_COMPATIBLE_MODE_SUFFIXES = ("/compatible-mode/v1", "/compatible-mode")


class DashScopeImageGenerationProvider(ImageGenerationProvider):
    """Image generation via the Bailian (DashScope) qwen-image sync API.

    Text-to-image and image-to-image editing share one endpoint: reference
    images are sent as extra content entries ahead of the prompt. Results come
    back as temporary URLs, which are downloaded and converted to base64 to
    match the rest of Onyx's image generation pipeline.
    """

    def __init__(self, api_key: str, api_base: str) -> None:
        self._api_key = api_key
        self._api_base = _normalize_api_base(api_base)

    @classmethod
    def validate_credentials(
        cls,
        credentials: ImageGenerationProviderCredentials,
    ) -> bool:
        return bool(credentials.api_key and credentials.api_base)

    @classmethod
    def _build_from_credentials(
        cls,
        credentials: ImageGenerationProviderCredentials,
    ) -> DashScopeImageGenerationProvider:
        if not credentials.api_key or not credentials.api_base:
            raise ImageProviderCredentialsError(
                "An API key and the workspace endpoint are required for Bailian image generation"
            )
        return cls(api_key=credentials.api_key, api_base=credentials.api_base)

    @property
    def supports_reference_images(self) -> bool:
        return True

    @property
    def max_reference_images(self) -> int:
        return _MAX_REFERENCE_IMAGES

    def generate_image(
        self,
        prompt: str,
        model: str,
        size: str,
        n: int,
        quality: str | None = None,
        reference_images: list[ReferenceImage] | None = None,
        **kwargs: Any,
    ) -> ImageGenerationResponse:
        # quality / response_format are OpenAI-isms the qwen-image API rejects.
        model_name = model.rsplit("/", 1)[-1]

        if reference_images and len(reference_images) > _MAX_REFERENCE_IMAGES:
            raise ValueError(
                f"Bailian image generation supports at most {_MAX_REFERENCE_IMAGES} reference images"
            )

        content: list[dict[str, str]] = []
        for image in reference_images or []:
            encoded = base64.b64encode(image.data).decode("utf-8")
            content.append({"image": f"data:{image.mime_type};base64,{encoded}"})
        content.append({"text": prompt})

        # The API defaults (watermark=false, prompt_extend=true) match what we
        # want, so only size and multi-image requests are sent explicitly.
        parameters: dict[str, Any] = {"size": size.replace("x", "*")}
        if n > 1:
            parameters["n"] = n

        payload = {
            "model": model_name,
            "input": {"messages": [{"role": "user", "content": content}]},
            "parameters": parameters,
        }

        flow = LLMFlow.IMAGE_EDIT if reference_images else LLMFlow.IMAGE_GENERATION
        with traced_llm_call(
            flow=flow,
            model=model_name,
            provider="dashscope",
            image_count=n,
            input_messages=[{"role": "user", "content": prompt}],
        ):
            image_urls = self._post_generation_request(payload)
            b64_images = _download_images_as_b64(image_urls)

        from litellm.types.utils import ImageObject, ImageResponse

        return ImageResponse(
            created=int(datetime.now().timestamp()),
            data=[
                ImageObject(b64_json=b64, revised_prompt=prompt)
                for b64 in b64_images
            ],
        )

    def _post_generation_request(self, payload: dict[str, Any]) -> list[str]:
        url = f"{self._api_base}{_IMAGE_GENERATION_PATH}"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        try:
            response = httpx.post(
                url, json=payload, headers=headers, timeout=_GENERATION_TIMEOUT_SECONDS
            )
        except httpx.HTTPError as e:
            raise RuntimeError(
                f"Could not reach the Bailian image generation endpoint: {e}"
            ) from e

        if response.status_code != 200:
            raise RuntimeError(_error_message(response))

        try:
            response_json = response.json()
        except ValueError as e:
            raise RuntimeError(
                "Invalid response from the Bailian image generation API"
            ) from e

        # Bailian reports API-level errors inside a 200 body.
        if "code" in response_json and "output" not in response_json:
            raise RuntimeError(_body_error_message(response_json))

        image_urls: list[str] = []
        choices = (response_json.get("output") or {}).get("choices") or []
        for choice in choices:
            content_items = (choice.get("message") or {}).get("content") or []
            for content_item in content_items:
                image_url = content_item.get("image")
                if image_url:
                    image_urls.append(str(image_url))

        if not image_urls:
            raise RuntimeError(
                "No image was returned from the Bailian image generation API"
            )
        return image_urls


def _normalize_api_base(api_base: str) -> str:
    """Reduce any accepted base shape to the bare workspace domain.

    Accepts ``https://{WorkspaceId}.{region}.maas.aliyuncs.com`` as well as the
    OpenAI-compatible variant ending in ``/compatible-mode/v1``.
    """
    cleaned = api_base.strip().rstrip("/")
    for suffix in _COMPATIBLE_MODE_SUFFIXES:
        if cleaned.endswith(suffix):
            cleaned = cleaned[: -len(suffix)]
            break
    return cleaned


def _error_message(response: httpx.Response) -> str:
    try:
        body = response.json()
        if "message" in body:
            return (
                f"Bailian image generation failed (HTTP {response.status_code}): "
                f"{body.get('code', '')} {body['message']}".strip()
            )
    except ValueError:
        pass
    return (
        f"Bailian image generation failed (HTTP {response.status_code}): "
        f"{response.text[:500]}"
    )


def _body_error_message(body: dict[str, Any]) -> str:
    message = f"Bailian image generation failed: {body.get('code', '')} "
    message += str(body.get("message", "")).strip()
    if body.get("request_id"):
        message += f" (request_id: {body['request_id']})"
    return message.strip()


def _download_images_as_b64(image_urls: list[str]) -> list[str]:
    """Result URLs are valid for 24 hours; fetch and inline them right away."""
    b64_images: list[str] = []
    for url in image_urls:
        try:
            response = httpx.get(
                url, timeout=_DOWNLOAD_TIMEOUT_SECONDS, follow_redirects=True
            )
        except httpx.HTTPError as e:
            raise RuntimeError(f"Failed to download the generated image: {e}") from e
        if response.status_code != 200:
            raise RuntimeError(
                f"Failed to download the generated image "
                f"(HTTP {response.status_code})"
            )
        b64_images.append(base64.b64encode(response.content).decode("utf-8"))
    return b64_images
