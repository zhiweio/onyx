from collections import Counter
from collections.abc import Sequence
from typing import Any

from onyx.llm.model_capabilities import (
    find_model_obj,
    get_llm_max_output_tokens,
    get_model_map,
    llm_max_input_tokens,
)
from onyx.llm.well_known_providers.llm_provider_options import (
    get_provider_display_name,
)
from onyx.server.gateway.models import (
    GatewayModality,
    GatewayModelCapabilities,
    GatewayModelDescriptor,
)
from onyx.server.manage.llm.models import LLMProviderView, ModelConfigurationView
from onyx.utils.logger import setup_logger

logger = setup_logger()


def gateway_provider_label(provider: LLMProviderView) -> str:
    return provider.name or get_provider_display_name(provider.provider)


def ordered_gateway_providers(
    providers: Sequence[LLMProviderView],
) -> list[LLMProviderView]:
    return sorted(
        providers,
        key=lambda provider: (gateway_provider_label(provider).casefold(), provider.id),
    )


def _model_display_name(model: ModelConfigurationView) -> str:
    return model.custom_display_name or model.display_name or model.name


def _capability_model_name(
    model_map: dict[str, Any],
    provider: LLMProviderView,
    model: ModelConfigurationView,
) -> str:
    if find_model_obj(model_map, provider.provider, model.name) is not None:
        return model.name

    deployment_name = provider.deployment_name
    if (
        deployment_name
        and find_model_obj(model_map, provider.provider, deployment_name) is not None
    ):
        logger.info(
            "Using deployment %r capabilities for gateway model alias %r",
            deployment_name,
            model.name,
        )
        return deployment_name

    return model.name


_GATEWAY_INPUT_MODALITIES: frozenset[str] = frozenset(
    {"text", "image", "video", "pdf"}
)
_GATEWAY_OUTPUT_MODALITIES: frozenset[str] = frozenset({"text"})


def _as_gateway_modalities(
    values: list[str],
    allowed: frozenset[str],
) -> tuple[GatewayModality, ...]:
    return tuple(value for value in values if value in allowed)  # type: ignore[misc]


def _gateway_input_modalities(
    model: ModelConfigurationView,
) -> tuple[GatewayModality, ...]:
    modalities = _as_gateway_modalities(
        model.input_modalities, _GATEWAY_INPUT_MODALITIES
    )
    if modalities:
        return modalities
    return ("text", "image") if model.supports_image_input else ("text",)


def _gateway_output_modalities(
    model: ModelConfigurationView,
) -> tuple[GatewayModality, ...]:
    modalities = _as_gateway_modalities(
        model.output_modalities, _GATEWAY_OUTPUT_MODALITIES
    )
    return modalities or ("text",)


def _gateway_token_limits(
    model_map: dict[str, Any],
    provider: LLMProviderView,
    model: ModelConfigurationView,
) -> tuple[int | None, int | None]:
    capability_model_name = _capability_model_name(model_map, provider, model)
    known = find_model_obj(model_map, provider.provider, capability_model_name) is not None
    max_input_tokens = model.configured_max_input_tokens
    if max_input_tokens is None and known:
        max_input_tokens = llm_max_input_tokens(
            model_map=model_map,
            model_name=capability_model_name,
            model_provider=provider.provider,
        )
    max_output_tokens = model.max_output_tokens
    if max_output_tokens is None and known:
        max_output_tokens = get_llm_max_output_tokens(
            model_map=model_map,
            model_name=capability_model_name,
            model_provider=provider.provider,
        )
    return max_input_tokens, max_output_tokens


def build_gateway_model_catalog(
    providers: Sequence[LLMProviderView],
) -> list[GatewayModelDescriptor]:
    """Build provider-neutral metadata for every visible accessible model.

    The order is deterministic because consumers reconcile serialized catalogs.
    """
    visible_models = [
        (provider, model)
        for provider in ordered_gateway_providers(providers)
        for model in sorted(
            (model for model in provider.model_configurations if model.is_visible),
            key=lambda model: model.name,
        )
    ]
    display_name_counts = Counter(
        _model_display_name(model) for _, model in visible_models
    )
    model_map = get_model_map()

    catalog: list[GatewayModelDescriptor] = []
    for provider, model in visible_models:
        display_name = _model_display_name(model)
        if display_name_counts[display_name] > 1:
            display_name = f"{display_name} ({gateway_provider_label(provider)})"

        input_modalities = _gateway_input_modalities(model)
        output_modalities = _gateway_output_modalities(model)
        max_input_tokens, max_output_tokens = _gateway_token_limits(
            model_map, provider, model
        )
        catalog.append(
            GatewayModelDescriptor(
                id=f"{provider.id}/{model.name}",
                display_name=display_name,
                provider=provider.provider,
                capabilities=GatewayModelCapabilities(
                    input_modalities=input_modalities,
                    output_modalities=output_modalities,
                    supports_reasoning=model.supports_reasoning,
                ),
                max_input_tokens=max_input_tokens,
                max_output_tokens=max_output_tokens,
            )
        )
    return catalog
