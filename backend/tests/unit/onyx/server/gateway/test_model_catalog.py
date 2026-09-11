from onyx.server.gateway.model_catalog import build_gateway_model_catalog
from onyx.server.manage.llm.models import LLMProviderView, ModelConfigurationView


def _model(
    name: str,
    *,
    visible: bool = True,
    supports_image_input: bool = False,
    supports_reasoning: bool = False,
) -> ModelConfigurationView:
    return ModelConfigurationView(
        name=name,
        display_name=name,
        is_visible=visible,
        supports_image_input=supports_image_input,
        supports_reasoning=supports_reasoning,
        input_modalities=["text", "image"] if supports_image_input else ["text"],
    )


def _provider(
    provider_id: int,
    provider_type: str,
    display_name: str,
    models: list[ModelConfigurationView],
) -> LLMProviderView:
    return LLMProviderView(
        id=provider_id,
        name=display_name,
        provider=provider_type,
        api_key=None,
        model_configurations=models,
    )


def test_catalog_filters_and_resolves_effective_gateway_capabilities() -> None:
    later_provider = _provider(
        8,
        "openai",
        "Zulu",
        [
            _model("text-model"),
            _model("hidden-model", visible=False, supports_image_input=True),
        ],
    )
    earlier_provider = _provider(
        3,
        "anthropic",
        "Alpha",
        [
            _model(
                "vision-reasoner",
                supports_image_input=True,
                supports_reasoning=True,
            )
        ],
    )

    catalog = build_gateway_model_catalog([later_provider, earlier_provider])

    assert [model.id for model in catalog] == [
        "3/vision-reasoner",
        "8/text-model",
    ]

    vision_model, text_model = catalog
    assert vision_model.provider == "anthropic"
    assert vision_model.capabilities.input_modalities == ("text", "image")
    assert vision_model.capabilities.output_modalities == ("text",)
    assert vision_model.capabilities.supports_reasoning is True
    assert vision_model.capabilities.supports_tool_calls is True
    assert vision_model.capabilities.supports_temperature is False
    assert vision_model.capabilities.supports_interleaved_reasoning is False

    assert text_model.provider == "openai"
    assert text_model.capabilities.input_modalities == ("text",)
    assert text_model.capabilities.supports_reasoning is False


def test_catalog_uses_admin_configured_max_input_tokens() -> None:
    local = _provider(
        1,
        "openai_compatible",
        "DeepSeek",
        [
            ModelConfigurationView(
                name="deepseek-v4-pro",
                display_name="DeepSeek V4 Pro",
                is_visible=True,
                supports_image_input=False,
                max_input_tokens=1_000_000,
                configured_max_input_tokens=1_000_000,
            )
        ],
    )
    catalog = build_gateway_model_catalog([local])
    assert catalog[0].max_input_tokens == 1_000_000
    assert catalog[0].max_output_tokens is not None

    limited = _provider(
        1,
        "openai_compatible",
        "DeepSeek",
        [
            ModelConfigurationView(
                name="deepseek-v4-pro",
                display_name="DeepSeek V4 Pro",
                is_visible=True,
                supports_image_input=False,
                max_input_tokens=131_072,
                configured_max_input_tokens=131_072,
            )
        ],
    )
    limited_catalog = build_gateway_model_catalog([limited])
    assert limited_catalog[0].max_input_tokens == 131_072


def test_catalog_uses_admin_modalities_and_output_tokens() -> None:
    catalog = build_gateway_model_catalog(
        [
            _provider(
                1,
                "openai",
                "OpenAI",
                [
                    ModelConfigurationView(
                        name="gpt-4o",
                        display_name="GPT-4o",
                        is_visible=True,
                        supports_image_input=True,
                        max_input_tokens=8000,
                        configured_max_input_tokens=8000,
                        max_output_tokens=2048,
                        input_modalities=["text", "pdf"],
                        output_modalities=["text"],
                    )
                ],
            )
        ]
    )
    assert catalog[0].max_input_tokens == 8000
    assert catalog[0].max_output_tokens == 2048
    assert catalog[0].capabilities.input_modalities == ("text", "pdf")
    assert catalog[0].capabilities.output_modalities == ("text",)
