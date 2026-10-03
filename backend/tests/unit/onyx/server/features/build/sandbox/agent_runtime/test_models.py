"""Unit tests for the agent model registry (snapshot, matrix, fingerprint)."""

from typing import Iterator

import pytest

from onyx.server.features.build.sandbox.agent_runtime import models as reg


class _Entry:
    """Minimal gateway-catalog entry satisfying the registry's Protocol."""

    def __init__(
        self,
        id: str,
        provider: str,
        display_name: str,
        max_input_tokens: int | None = None,
        max_output_tokens: int | None = None,
    ) -> None:
        self.id = id
        self.provider = provider
        self.display_name = display_name
        self.max_input_tokens = max_input_tokens
        self.max_output_tokens = max_output_tokens


_SNAPSHOT = [
    _Entry("1/glm-main", "bigmodel", "GLM-Main", 200_000, 32_768),
    _Entry("1/glm-air", "bigmodel", "GLM-Air", 128_000, 16_384),
    _Entry("2/qwen", "dashscope", "Qwen", 131_072, 16_384),
    _Entry("3/claude", "anthropic", "Claude", 200_000, 32_768),
]


@pytest.fixture(autouse=True)
def _snapshot() -> Iterator[None]:
    reg.apply_model_catalog_cache(_SNAPSHOT, "1/glm-main")
    yield
    reg.apply_model_catalog_cache([], None)


def test_snapshot_is_applied_with_single_default() -> None:
    models = reg.iter_models()
    assert [spec.model_id for spec in models] == [
        "1/glm-main",
        "1/glm-air",
        "2/qwen",
        "3/claude",
    ]
    defaults = [spec for spec in models if spec.is_default]
    assert [spec.model_id for spec in defaults] == ["1/glm-main"]


def test_spec_fields_come_from_the_catalog_entry() -> None:
    spec = reg.get_model_spec("1/glm-main")
    assert spec is not None
    assert spec.provider == "bigmodel"
    assert spec.display_name == "GLM-Main"
    assert spec.context_window == 200_000
    assert spec.max_output_tokens == 32_768


def test_default_model_is_driveable_by_opencode() -> None:
    model_id = reg.default_model_for("opencode")
    assert model_id is not None
    assert reg.model_supported_by(model_id, "opencode")


def test_support_matrix_follows_provider_type() -> None:
    assert reg.model_supported_by("1/glm-main", "opencode")
    assert reg.model_supported_by("1/glm-main", "codex")
    # anthropic-provider models answer the anthropic-messages surface,
    # which codex cannot drive.
    assert not reg.model_supported_by("3/claude", "codex")
    assert reg.model_supported_by("3/claude", "opencode")
    assert not reg.model_supported_by("1/glm-main", "pi")
    assert not reg.model_supported_by("missing-model", "opencode")


def test_default_falls_back_when_default_not_driveable() -> None:
    reg.apply_model_catalog_cache(_SNAPSHOT, "3/claude")
    model_id = reg.default_model_for("codex")
    assert model_id == "1/glm-main"


def test_unknown_model_has_no_default_and_no_fingerprint() -> None:
    assert reg.get_model_spec("missing-model") is None
    assert reg.default_model_for("pi") is None
    assert reg.fingerprint("missing-model", "rev1") is None


def test_empty_snapshot_clears_the_registry() -> None:
    reg.apply_model_catalog_cache([], None)
    assert reg.iter_models() == ()
    assert reg.default_model_for("opencode") is None


def test_fingerprint_changes_with_credential_revision_and_spec() -> None:
    base = reg.fingerprint("1/glm-main", "rev1", gateway_route="default")
    assert base is not None
    assert reg.fingerprint("1/glm-main", "rev1", gateway_route="default") == base
    # Credential change invalidates.
    assert reg.fingerprint("1/glm-main", "rev2", gateway_route="default") != base
    # Gateway change invalidates.
    assert reg.fingerprint("1/glm-main", "rev1", gateway_route="other") != base
    # Different model with same inputs produces a different fingerprint.
    assert reg.fingerprint("1/glm-air", "rev1", gateway_route="default") != base


def test_classify_provider_error_codes() -> None:
    import httpx

    assert reg.classify_provider_error(TimeoutError()) == reg.PROBE_FAILURE_TIMEOUT
    unauthorized = httpx.HTTPStatusError(
        "401",
        request=httpx.Request("GET", "https://provider.example/v1/models"),
        response=httpx.Response(401),
    )
    assert reg.classify_provider_error(unauthorized) == reg.PROBE_FAILURE_ACCESS_DENIED
    assert reg.classify_provider_error(RuntimeError("rate limit exceeded")) == (
        reg.PROBE_FAILURE_QUOTA
    )
    assert reg.classify_provider_error(RuntimeError("model not found")) == (
        reg.PROBE_FAILURE_MODEL_UNAVAILABLE
    )
    assert reg.classify_provider_error(RuntimeError("boom")) == (
        reg.PROBE_FAILURE_PROVIDER
    )


def test_probe_model_success_and_failure() -> None:
    ok, failure = reg.probe_model("1/glm-main", lambda: "OK")
    assert ok and failure is None

    ok, failure = reg.probe_model(
        "1/glm-main", lambda: (_ for _ in ()).throw(RuntimeError("401"))
    )
    assert not ok
    assert failure == reg.PROBE_FAILURE_ACCESS_DENIED

    ok, failure = reg.probe_model("missing-model", lambda: "OK")
    assert not ok and failure == reg.PROBE_FAILURE_UNKNOWN_MODEL

    ok, failure = reg.probe_model("1/glm-main", lambda: "   ")
    assert not ok and failure == reg.PROBE_FAILURE_PROVIDER
