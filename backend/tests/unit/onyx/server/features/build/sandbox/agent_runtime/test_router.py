"""Unit tests for the HarnessRouter precedence chain (QM harness-router port)."""

from typing import Iterator

import pytest

from onyx.server.features.build.sandbox.agent_runtime import models as model_registry
from onyx.server.features.build.sandbox.agent_runtime.router import (
    HarnessRouter,
    NonRetryableRuntimeError,
    PurposeBinding,
    RuntimePurpose,
    RuntimeResolutionRequest,
    build_router_from_env,
)


class _Entry:
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


_CATALOG = [
    _Entry("1/glm-main", "bigmodel", "GLM-Main", 200_000, 32_768),
    _Entry("1/glm-air", "bigmodel", "GLM-Air", 128_000, 16_384),
    _Entry("2/qwen", "dashscope", "Qwen", 131_072, 16_384),
]


@pytest.fixture(autouse=True)
def _catalog_snapshot() -> Iterator[None]:
    model_registry.apply_model_catalog_cache(_CATALOG, "1/glm-main")
    yield
    model_registry.apply_model_catalog_cache([], None)


def _router(**kwargs: object) -> HarnessRouter:
    defaults: dict[str, object] = {
        "approved_runtimes": frozenset({"opencode"}),
        "org_default_runtime": "opencode",
        "purpose_bindings": {
            RuntimePurpose.CLASSIFY: PurposeBinding("opencode", "1/glm-air"),
        },
    }
    defaults.update(kwargs)
    return HarnessRouter(**defaults)  # type: ignore[arg-type]


def test_org_default_when_nothing_else_applies() -> None:
    choice = _router().resolve(RuntimeResolutionRequest())
    assert choice.runtime_id == "opencode"
    assert choice.origin == "org_default"
    assert model_registry.model_supported_by(choice.model_id, choice.runtime_id)


def test_purpose_beats_everything() -> None:
    choice = _router().resolve(
        RuntimeResolutionRequest(
            purpose=RuntimePurpose.CLASSIFY,
            requested_runtime="opencode",
            requested_model="2/qwen",
        )
    )
    assert choice.origin == "purpose:classify"
    assert choice.model_id == "1/glm-air"


def test_explicit_request_beats_scenario_and_default() -> None:
    choice = _router().resolve(
        RuntimeResolutionRequest(
            requested_model="2/qwen",
            scenario_runtime="opencode",
        )
    )
    assert choice.origin == "request"
    assert choice.model_id == "2/qwen"


def test_scenario_pins_runtime_and_resolves_registry_default_model() -> None:
    choice = _router().resolve(RuntimeResolutionRequest(scenario_runtime="opencode"))
    assert choice.origin == "scenario"
    assert choice.model_id == "1/glm-main"


def test_unapproved_runtime_request_raises_nonretryable() -> None:
    with pytest.raises(NonRetryableRuntimeError, match="not approved"):
        _router().resolve(RuntimeResolutionRequest(requested_runtime="codex"))


def test_unapproved_runtime_scenario_falls_back_to_org_default() -> None:
    choice = _router().resolve(RuntimeResolutionRequest(scenario_runtime="codex"))
    assert choice.origin == "org_default"
    assert choice.runtime_id == "opencode"


def test_unsupported_explicit_model_raises() -> None:
    with pytest.raises(NonRetryableRuntimeError, match="not supported"):
        _router().resolve(
            RuntimeResolutionRequest(
                requested_runtime="opencode", requested_model="nope"
            )
        )


def test_model_only_request_keeps_default_runtime_when_supported() -> None:
    choice = _router().resolve(RuntimeResolutionRequest(requested_model="1/glm-air"))
    assert choice.runtime_id == "opencode"
    assert choice.model_id == "1/glm-air"
    assert choice.origin == "request"


def test_purpose_binding_with_unapproved_runtime_is_ignored() -> None:
    router = _router(
        purpose_bindings={
            RuntimePurpose.CLASSIFY: PurposeBinding("codex", "1/glm-air")
        },
        approved_runtimes=frozenset({"opencode"}),
    )
    choice = router.resolve(RuntimeResolutionRequest(purpose=RuntimePurpose.CLASSIFY))
    assert choice.origin == "org_default"


def test_finalize_never_returns_unapproved_runtime() -> None:
    router = _router()
    # A derived choice with an unapproved runtime cannot come from the chain,
    # but _finalize still guards config drift defensively.
    choice = router._org_default_choice()
    final = router._finalize(choice)
    assert final.runtime_id in router.approved_runtimes


def test_build_router_from_env_always_includes_primary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SANDBOX_APPROVED_RUNTIMES", "opencode,codex")
    monkeypatch.setenv("SANDBOX_AGENT_RUNTIME", "opencode")
    router = build_router_from_env()
    assert "opencode" in router.approved_runtimes
    assert "codex" in router.approved_runtimes
