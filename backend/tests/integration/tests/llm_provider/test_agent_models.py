"""Integration tests: the agent-model registry mirrors the provider config.

The "Agent Sandbox Models" admin tab is a read-only view over the gateway
catalog — every visible model of every accessible LLM provider. These
tests lock that single-source guarantee, including coverage of
non-OpenAI-compatible provider types.
"""

from onyx.llm.constants import LlmProviderNames
from onyx.server.manage.llm.models import (
    LLMProviderUpsertRequest,
    ModelConfigurationUpsertRequest,
)
from tests.integration.common_utils.constants import API_SERVER_URL
from tests.integration.common_utils.http_client import client
from tests.integration.common_utils.managers.user import UserManager
from tests.integration.common_utils.test_models import DATestUser


def _create_provider(
    admin_user: DATestUser,
    provider: str,
    models: list[ModelConfigurationUpsertRequest],
    api_key: str = "test-key",
) -> int:
    """Create a provider row directly so tests control per-model visibility."""
    request = LLMProviderUpsertRequest(
        name=f"agent-models-test-{provider}",
        provider=provider,
        api_key=api_key,
        api_key_changed=True,
        is_public=True,
        model_configurations=models,
    )
    response = client.put(
        f"{API_SERVER_URL}/admin/llm/provider?is_creation=true",
        json=request.model_dump(),
        headers=admin_user.headers,
    )
    response.raise_for_status()
    return int(response.json()["id"])


def _list_agent_models(admin_user: DATestUser) -> list[dict]:
    response = client.get(
        f"{API_SERVER_URL}/admin/agent-models",
        headers=admin_user.headers,
    )
    response.raise_for_status()
    return response.json()["models"]


def _wire_id(provider_id: int, model_name: str) -> str:
    return f"{provider_id}/{model_name}"


def test_agent_models_mirror_provider_config() -> None:
    admin_user = UserManager.create(name="agent-models-admin")

    openai_provider_id = _create_provider(
        admin_user,
        LlmProviderNames.OPENAI,
        [
            ModelConfigurationUpsertRequest(
                name="gpt-test-visible",
                is_visible=True,
                max_input_tokens=128_000,
                display_name="GPT Test Visible",
                supports_image_input=False,
            ),
            ModelConfigurationUpsertRequest(
                name="gpt-test-hidden",
                is_visible=False,
                max_input_tokens=8_000,
                display_name="GPT Test Hidden",
                supports_image_input=False,
            ),
        ],
    )
    # A non-OpenAI-compatible provider type must surface through the same
    # gateway catalog (credentials/protocol translation happen server-side).
    anthropic_provider_id = _create_provider(
        admin_user,
        LlmProviderNames.ANTHROPIC,
        [
            ModelConfigurationUpsertRequest(
                name="claude-test-visible",
                is_visible=True,
                max_input_tokens=200_000,
                display_name="Claude Test Visible",
                supports_image_input=False,
            ),
        ],
    )
    # A provider without any visible model contributes nothing.
    hidden_only_provider_id = _create_provider(
        admin_user,
        LlmProviderNames.DEEPSEEK,
        [
            ModelConfigurationUpsertRequest(
                name="deepseek-test-hidden",
                is_visible=False,
                max_input_tokens=None,
                display_name="DeepSeek Test Hidden",
                supports_image_input=False,
            ),
        ],
    )

    try:
        models = _list_agent_models(admin_user)
        by_id = {model["model_id"]: model for model in models}

        visible = by_id[_wire_id(openai_provider_id, "gpt-test-visible")]
        assert visible["provider"] == LlmProviderNames.OPENAI
        assert visible["provider_id"] == openai_provider_id
        assert visible["context_window"] == 128_000
        assert "opencode" in visible["runtimes"]

        # Hidden models stay out of the sandbox view.
        assert _wire_id(openai_provider_id, "gpt-test-hidden") not in by_id
        # Providers without a visible model never appear.
        assert not any(
            model["provider_id"] == hidden_only_provider_id for model in models
        )

        # Non-OpenAI-compatible coverage guarantee.
        claude = by_id[_wire_id(anthropic_provider_id, "claude-test-visible")]
        assert claude["provider"] == LlmProviderNames.ANTHROPIC
        assert claude["runtimes"] == ["opencode"]
        assert "codex" in visible["runtimes"]
    finally:
        for provider_id in (
            openai_provider_id,
            anthropic_provider_id,
            hidden_only_provider_id,
        ):
            client.delete(
                f"{API_SERVER_URL}/admin/llm/provider/{provider_id}?force=true",
                headers=admin_user.headers,
            )


def test_default_marker_follows_craft_default() -> None:
    admin_user = UserManager.create(name="agent-models-default-admin")

    provider_id = _create_provider(
        admin_user,
        LlmProviderNames.OPENAI,
        [
            ModelConfigurationUpsertRequest(
                name="gpt-test-default",
                is_visible=True,
                max_input_tokens=None,
                display_name="GPT Test Default",
                supports_image_input=False,
            ),
        ],
    )
    other_provider_id = _create_provider(
        admin_user,
        LlmProviderNames.OPENAI,
        [
            ModelConfigurationUpsertRequest(
                name="gpt-test-other",
                is_visible=True,
                max_input_tokens=None,
                display_name="GPT Test Other",
                supports_image_input=False,
            ),
        ],
    )

    try:
        response = client.post(
            f"{API_SERVER_URL}/admin/llm/default-craft",
            json={
                "provider_id": provider_id,
                "model_name": "gpt-test-default",
            },
            headers=admin_user.headers,
        )
        response.raise_for_status()

        models = _list_agent_models(admin_user)
        by_id = {model["model_id"]: model for model in models}
        assert by_id[_wire_id(provider_id, "gpt-test-default")]["is_default"]
        assert not by_id[_wire_id(other_provider_id, "gpt-test-other")]["is_default"]
    finally:
        client.delete(
            f"{API_SERVER_URL}/admin/llm/default-craft",
            headers=admin_user.headers,
        )
        for stale_provider_id in (provider_id, other_provider_id):
            client.delete(
                f"{API_SERVER_URL}/admin/llm/provider/{stale_provider_id}?force=true",
                headers=admin_user.headers,
            )
