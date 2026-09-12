from datetime import datetime, timezone

import pytest

from onyx.llm.well_known_providers.auto_update_models import (
    LLMProviderRecommendation,
    LLMRecommendations,
)
from onyx.llm.constants import (
    LlmProviderNames,
    WELL_KNOWN_PROVIDER_NAMES,
    litellm_provider_name,
)
from onyx.llm.well_known_providers.constants import (
    BIGMODEL_API_BASE,
    DEFAULT_API_BASE_FOR_PROVIDER,
    OPENAI_PROVIDER_NAME,
    VERTEXAI_PROVIDER_NAME,
)
from onyx.llm.model_capabilities import (
    get_max_input_tokens,
    litellm_thinks_model_supports_image_input,
)
from onyx.llm.well_known_providers.llm_provider_options import (
    _merge_missing_provider_recommendations,
    get_deepseek_model_names,
    get_minimax_model_names,
    get_moonshot_model_names,
    get_zai_model_names,
    is_obsolete_model,
    is_well_known_provider_model,
    model_configurations_for_provider,
    visible_models_for_provider,
)
from onyx.llm.well_known_providers.models import SimpleKnownModel


def test_get_visible_models_dedupes_default_and_prefers_display_name() -> None:
    # The default is repeated in additional_visible_models (where it carries a
    # display name); get_visible_models must return it once, with the name.
    recommendations = LLMRecommendations(
        version="test",
        updated_at=datetime.now(timezone.utc),
        providers={
            "anthropic": LLMProviderRecommendation(
                default_model=SimpleKnownModel(name="claude-opus-4-8"),
                additional_visible_models=[
                    SimpleKnownModel(
                        name="claude-opus-4-8", display_name="Claude Opus 4.8"
                    ),
                    SimpleKnownModel(
                        name="claude-sonnet-4-6", display_name="Claude Sonnet 4.6"
                    ),
                ],
            )
        },
    )

    visible = recommendations.get_visible_models("anthropic")

    assert [(m.name, m.display_name) for m in visible] == [
        ("claude-opus-4-8", "Claude Opus 4.8"),
        ("claude-sonnet-4-6", "Claude Sonnet 4.6"),
    ]


def _build_recommendations(
    provider_name: str, visible_model_names: list[str]
) -> LLMRecommendations:
    return LLMRecommendations(
        version="test",
        updated_at=datetime.now(timezone.utc),
        providers={
            provider_name: LLMProviderRecommendation(
                default_model=SimpleKnownModel(name=visible_model_names[0]),
                additional_visible_models=[
                    SimpleKnownModel(name=model_name)
                    for model_name in visible_model_names[1:]
                ],
            )
        },
    )


def test_model_configurations_vertex_are_sorted_by_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "onyx.llm.well_known_providers.llm_provider_options.fetch_models_for_provider",
        lambda _provider_name: ["zeta-model", "alpha-model", "Beta-model"],
    )
    monkeypatch.setattr(
        "onyx.llm.well_known_providers.llm_provider_options.get_max_input_tokens",
        lambda _model_name, _provider_name: None,
    )
    monkeypatch.setattr(
        "onyx.llm.well_known_providers.llm_provider_options.model_supports_image_input",
        lambda _model_name, _provider_name: False,
    )

    recommendations = _build_recommendations(
        VERTEXAI_PROVIDER_NAME, ["gamma-model", "alpha-model"]
    )

    model_configurations = model_configurations_for_provider(
        VERTEXAI_PROVIDER_NAME, recommendations
    )

    assert [model.name for model in model_configurations] == [
        "alpha-model",
        "Beta-model",
        "gamma-model",
        "zeta-model",
    ]
    assert [model.is_visible for model in model_configurations] == [
        True,
        False,
        True,
        False,
    ]


def test_model_configurations_carry_display_name_and_dedupe_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The default is repeated in additional_visible_models (where it carries a
    # display name); the result must be deduped and carry that display name.
    monkeypatch.setattr(
        "onyx.llm.well_known_providers.llm_provider_options.fetch_models_for_provider",
        lambda _provider_name: [],
    )
    monkeypatch.setattr(
        "onyx.llm.well_known_providers.llm_provider_options.get_max_input_tokens",
        lambda _model_name, _provider_name: None,
    )
    monkeypatch.setattr(
        "onyx.llm.well_known_providers.llm_provider_options.model_supports_image_input",
        lambda _model_name, _provider_name: False,
    )

    recommendations = LLMRecommendations(
        version="test",
        updated_at=datetime.now(timezone.utc),
        providers={
            "anthropic": LLMProviderRecommendation(
                default_model=SimpleKnownModel(name="claude-opus-4-8"),
                additional_visible_models=[
                    SimpleKnownModel(
                        name="claude-opus-4-8", display_name="Claude Opus 4.8"
                    ),
                    SimpleKnownModel(
                        name="claude-sonnet-4-6", display_name="Claude Sonnet 4.6"
                    ),
                ],
            )
        },
    )

    model_configurations = model_configurations_for_provider(
        "anthropic", recommendations
    )

    assert [m.name for m in model_configurations] == [
        "claude-opus-4-8",
        "claude-sonnet-4-6",
    ]
    by_name = {m.name: m for m in model_configurations}
    assert by_name["claude-opus-4-8"].display_name == "Claude Opus 4.8"
    assert all(m.is_visible for m in model_configurations)
    # Only the config's default model is flagged as the recommended default.
    assert by_name["claude-opus-4-8"].is_recommended_default is True
    assert by_name["claude-sonnet-4-6"].is_recommended_default is False


def test_model_configurations_non_vertex_preserve_provider_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "onyx.llm.well_known_providers.llm_provider_options.fetch_models_for_provider",
        lambda _provider_name: ["model-b", "model-a"],
    )
    monkeypatch.setattr(
        "onyx.llm.well_known_providers.llm_provider_options.get_max_input_tokens",
        lambda _model_name, _provider_name: None,
    )
    monkeypatch.setattr(
        "onyx.llm.well_known_providers.llm_provider_options.model_supports_image_input",
        lambda _model_name, _provider_name: False,
    )

    recommendations = _build_recommendations(
        OPENAI_PROVIDER_NAME, ["model-c", "model-a"]
    )

    model_configurations = model_configurations_for_provider(
        OPENAI_PROVIDER_NAME, recommendations
    )

    assert [model.name for model in model_configurations] == [
        "model-b",
        "model-a",
        "model-c",
    ]


def test_merge_fills_providers_missing_from_github() -> None:
    remote = LLMRecommendations(
        version="remote",
        updated_at=datetime.now(timezone.utc),
        providers={
            "openai": LLMProviderRecommendation(
                default_model=SimpleKnownModel(name="gpt-5.6-sol"),
            )
        },
    )
    bundled = LLMRecommendations(
        version="bundled",
        updated_at=datetime.now(timezone.utc),
        providers={
            "openai": LLMProviderRecommendation(
                default_model=SimpleKnownModel(name="should-not-win"),
            ),
            "deepseek": LLMProviderRecommendation(
                default_model=SimpleKnownModel(name="deepseek-v4-pro"),
            ),
        },
    )

    merged = _merge_missing_provider_recommendations(remote, bundled)

    assert merged.get_default_model("openai") is not None
    assert merged.get_default_model("openai").name == "gpt-5.6-sol"
    assert merged.get_default_model("deepseek") is not None
    assert merged.get_default_model("deepseek").name == "deepseek-v4-pro"
    assert _merge_missing_provider_recommendations(None, bundled) is bundled


def test_deepseek_and_zai_are_well_known() -> None:
    assert LlmProviderNames.DEEPSEEK in WELL_KNOWN_PROVIDER_NAMES
    assert LlmProviderNames.ZAI in WELL_KNOWN_PROVIDER_NAMES
    assert LlmProviderNames.BIGMODEL in WELL_KNOWN_PROVIDER_NAMES
    assert LlmProviderNames.MOONSHOT in WELL_KNOWN_PROVIDER_NAMES
    assert LlmProviderNames.MINIMAX in WELL_KNOWN_PROVIDER_NAMES
    assert litellm_provider_name(LlmProviderNames.BIGMODEL) == LlmProviderNames.ZAI
    assert DEFAULT_API_BASE_FOR_PROVIDER[LlmProviderNames.BIGMODEL] == BIGMODEL_API_BASE


def test_get_deepseek_model_names_strips_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import litellm

    monkeypatch.setattr(
        litellm,
        "deepseek_models",
        [
            "deepseek-chat",
            "deepseek/deepseek-v4-pro",
            "deepseek/deepseek-chat",
            "deepseek/deepseek-v4-flash",
            "deepseek-reasoner",
            "deepseek/deepseek-v4-flash-vision-exp",
        ],
    )

    assert get_deepseek_model_names() == [
        "deepseek-v4-pro",
        "deepseek-flash",
    ]
    assert not is_obsolete_model("deepseek-flash", LlmProviderNames.DEEPSEEK)
    assert is_obsolete_model("deepseek-v4-flash", LlmProviderNames.DEEPSEEK)
    assert is_obsolete_model(
        "deepseek-v4-flash-vision-exp", LlmProviderNames.DEEPSEEK
    )
    assert get_max_input_tokens("deepseek-flash", LlmProviderNames.DEEPSEEK) > 900_000
    assert litellm_thinks_model_supports_image_input(
        "deepseek-flash", LlmProviderNames.DEEPSEEK
    )


def test_visible_models_for_provider_adds_official_deepseek_flash() -> None:
    recommendations = LLMRecommendations(
        version="stale",
        updated_at=datetime.now(timezone.utc),
        providers={
            "deepseek": LLMProviderRecommendation(
                default_model=SimpleKnownModel(name="deepseek-v4-pro"),
                additional_visible_models=[
                    SimpleKnownModel(
                        name="deepseek-v4-pro", display_name="DeepSeek V4 Pro"
                    ),
                    SimpleKnownModel(
                        name="deepseek-v4-flash", display_name="DeepSeek V4 Flash"
                    ),
                ],
            )
        },
    )

    visible = visible_models_for_provider("deepseek", recommendations)
    names = [model.name for model in visible]
    assert "deepseek-v4-pro" in names
    assert "deepseek-flash" in names
    assert "deepseek-v4-flash" not in names
    assert is_well_known_provider_model("deepseek", "deepseek-flash")
    assert not is_well_known_provider_model("deepseek", "deepseek-chat")


def test_get_zai_model_names_strips_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    import litellm

    monkeypatch.setattr(
        litellm,
        "zai_models",
        ["zai/glm-4.7", "glm-4.6", "zai/glm-4.6"],
    )

    assert get_zai_model_names() == ["glm-4.7", "glm-4.6"]


def test_get_moonshot_model_names_strips_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import litellm

    monkeypatch.setattr(
        litellm,
        "moonshot_models",
        ["kimi-k3", "moonshot/kimi-k2.6", "moonshot/kimi-k3"],
    )

    assert get_moonshot_model_names() == ["kimi-k3", "kimi-k2.6"]


def test_get_minimax_model_names_drops_speech(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import litellm

    monkeypatch.setattr(
        litellm,
        "minimax_models",
        ["minimax/MiniMax-M2.5", "MiniMax-M3", "minimax/speech-2.6-hd"],
    )

    assert get_minimax_model_names() == ["MiniMax-M3", "MiniMax-M2.5"]
