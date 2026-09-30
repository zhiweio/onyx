"""Unit tests for agent model overlays: merge semantics + API validation."""

from dataclasses import dataclass


from onyx.server.features.build.sandbox.agent_runtime import models as reg


@dataclass
class OverlayRow:
    name: str
    provider: str
    template_model_id: str
    model_id: str
    context_window: int | None = None
    max_output_tokens: int | None = None
    base_url: str | None = None
    enabled: bool = True


def test_overlay_inherits_and_overrides_template() -> None:
    row = OverlayRow(
        name="客户私有GLM",
        provider="bigmodel",
        template_model_id="glm-4.7",
        model_id="glm-4.7-private",
        context_window=128_000,
        base_url="https://llm.customer.cn/v1",
    )
    spec = reg.overlay_spec(row)
    assert spec is not None
    assert spec.model_id == "glm-4.7-private"
    assert spec.context_window == 128_000  # overridden
    assert spec.max_output_tokens == reg.get_model_spec("glm-4.7").max_output_tokens
    assert spec.runtimes == reg.get_model_spec("glm-4.7").runtimes  # inherited
    assert "llm.customer.cn" in spec.notes


def test_overlay_unknown_template_rejected() -> None:
    assert reg.overlay_spec(OverlayRow("x", "p", "nope", "m")) is None


def test_merge_overlays_semantics() -> None:
    rows = [
        OverlayRow("私有Qwen", "dashscope", "qwen3-plus", "qwen3-plus-private"),
        OverlayRow("禁用", "dashscope", "qwen3-max", "qwen3-max-off", enabled=False),
        OverlayRow("坏模板", "p", "unknown-template", "bad"),
        OverlayRow("撞默认", "bigmodel", "glm-4.7", "glm-4.7"),  # collides with default
    ]
    merged = {s.model_id: s for s in reg.merge_overlays(rows)}
    assert "qwen3-plus-private" in merged
    assert "qwen3-max-off" not in merged  # disabled
    assert "bad" not in merged  # unknown template
    assert merged["glm-4.7"].is_default  # default not shadowed
    # the runtime overlay cache makes the router support matrix overlay-aware
    reg.apply_overlay_cache(rows)
    try:
        assert reg.model_supported_by("qwen3-plus-private", "opencode")
        assert reg.get_model_spec("qwen3-plus-private") is not None
        assert reg.get_model_spec("qwen3-max-off") is None  # disabled excluded
    finally:
        reg.apply_overlay_cache([])
