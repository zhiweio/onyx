from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import openai
import pytest

from onyx.natural_language_processing.constants import (
    DEFAULT_DASHSCOPE_API_BASE,
    DEFAULT_DASHSCOPE_MODEL,
)
from onyx.natural_language_processing.search_nlp_models import CloudEmbedding
from shared_configs.enums import EmbeddingProvider, EmbedTextType

_SAMPLE_EMBEDDINGS = [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]


def _mock_response_for(texts: list[str]) -> MagicMock:
    response = MagicMock()
    # One embedding per input text; the values are irrelevant, only the count
    # matters for batching assertions.
    response.data = [MagicMock(embedding=[0.0]) for _ in texts]
    return response


def _mock_dashscope_client() -> tuple[Any, AsyncMock]:
    mock_client = AsyncMock()
    mock_client.embeddings.create = AsyncMock(
        side_effect=lambda **kwargs: _mock_response_for(kwargs["input"])
    )
    return mock_client, mock_client.embeddings.create


@pytest.mark.asyncio
async def test_dashscope_embed_defaults_to_compatible_mode_base() -> None:
    """Without an api_url the client targets the Beijing compatible-mode base
    and falls back to the default DashScope embedding model."""
    mock_client, mock_create = _mock_dashscope_client()
    with patch("openai.AsyncOpenAI", return_value=mock_client) as mock_openai:
        async with CloudEmbedding("fake-key", EmbeddingProvider.DASHSCOPE) as embedding:
            result = await embedding.embed(
                texts=["hello"],
                text_type=EmbedTextType.PASSAGE,
                model_name=None,
            )

    assert mock_openai.call_args.kwargs["base_url"] == DEFAULT_DASHSCOPE_API_BASE
    await_args = mock_create.await_args
    assert await_args is not None
    assert await_args.kwargs["model"] == DEFAULT_DASHSCOPE_MODEL
    assert await_args.kwargs["input"] == ["hello"]
    assert result == [[0.0]]


@pytest.mark.asyncio
async def test_dashscope_embed_uses_credential_api_url() -> None:
    """The credentials' api_url (workspace/region base) wins over the default."""
    mock_client, mock_create = _mock_dashscope_client()
    workspace_base = "https://ws-1234.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
    with patch("openai.AsyncOpenAI", return_value=mock_client) as mock_openai:
        async with CloudEmbedding(
            "fake-key", EmbeddingProvider.DASHSCOPE, api_url=workspace_base
        ) as embedding:
            await embedding.embed(
                texts=["hello"],
                text_type=EmbedTextType.QUERY,
                model_name="text-embedding-v3",
            )

    assert mock_openai.call_args.kwargs["base_url"] == workspace_base
    await_args = mock_create.await_args
    assert await_args is not None
    assert await_args.kwargs["model"] == "text-embedding-v3"


@pytest.mark.asyncio
async def test_dashscope_embed_batches_at_ten_texts() -> None:
    """DashScope accepts at most 10 input texts per request, so 25 texts must
    split into calls of 10 / 10 / 5."""
    mock_client, mock_create = _mock_dashscope_client()
    texts = [f"text_{i}" for i in range(25)]
    with patch("openai.AsyncOpenAI", return_value=mock_client):
        async with CloudEmbedding("fake-key", EmbeddingProvider.DASHSCOPE) as embedding:
            result = await embedding.embed(
                texts=texts,
                text_type=EmbedTextType.PASSAGE,
                model_name="text-embedding-v4",
            )

    assert mock_create.await_count == 3
    batch_sizes = [len(call.kwargs["input"]) for call in mock_create.await_args_list]
    assert batch_sizes == [10, 10, 5]
    assert len(result) == 25


@pytest.mark.asyncio
async def test_dashscope_embed_passes_reduced_dimension() -> None:
    mock_client, mock_create = _mock_dashscope_client()
    with patch("openai.AsyncOpenAI", return_value=mock_client):
        async with CloudEmbedding("fake-key", EmbeddingProvider.DASHSCOPE) as embedding:
            await embedding.embed(
                texts=["hello"],
                text_type=EmbedTextType.PASSAGE,
                model_name="text-embedding-v4",
                reduced_dimension=768,
            )

    await_args = mock_create.await_args
    assert await_args is not None
    assert await_args.kwargs["dimensions"] == 768


@pytest.mark.asyncio
async def test_dashscope_embed_omits_dimensions_when_unset() -> None:
    mock_client, mock_create = _mock_dashscope_client()
    with patch("openai.AsyncOpenAI", return_value=mock_client):
        async with CloudEmbedding("fake-key", EmbeddingProvider.DASHSCOPE) as embedding:
            await embedding.embed(
                texts=["hello"],
                text_type=EmbedTextType.PASSAGE,
                model_name="text-embedding-v4",
            )

    await_args = mock_create.await_args
    assert await_args is not None
    assert await_args.kwargs["dimensions"] is openai.omit
