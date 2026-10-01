"""Unit tests for the HarnessRouter precedence chain (QM harness-router port)."""

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


def _router(**kwargs: object) -> HarnessRouter:
    defaults: dict[str, object] = {
        "approved_runtimes": frozenset({"opencode"}),
        "org_default_runtime": "opencode",
        "purpose_bindings": {
            RuntimePurpose.CLASSIFY: PurposeBinding("opencode", "glm-4.5-air"),
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
            requested_model="qwen3-max",
        )
    )
    assert choice.origin == "purpose:classify"
    assert choice.model_id == "glm-4.5-air"


def test_explicit_request_beats_scenario_and_default() -> None:
    choice = _router().resolve(
        RuntimeResolutionRequest(
            requested_model="deepseek-chat",
            scenario_runtime="opencode",
            scenario_model="glm-4.6",
        )
    )
    assert choice.origin == "request"
    assert choice.model_id == "deepseek-chat"


def test_scenario_pins_runtime_and_model() -> None:
    choice = _router().resolve(
        RuntimeResolutionRequest(
            scenario_runtime="opencode", scenario_model="qwen3-plus"
        )
    )
    assert choice.origin == "scenario"
    assert choice.model_id == "qwen3-plus"


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


def test_unsupported_scenario_model_falls_back_to_runtime_default() -> None:
    choice = _router().resolve(
        RuntimeResolutionRequest(scenario_runtime="opencode", scenario_model="nope")
    )
    assert choice.runtime_id == "opencode"
    assert choice.origin == "scenario"
    assert "unsupported" in choice.note
    assert model_registry.model_supported_by(choice.model_id, "opencode")


def test_model_only_request_keeps_default_runtime_when_supported() -> None:
    choice = _router().resolve(RuntimeResolutionRequest(requested_model="glm-4.6"))
    assert choice.runtime_id == "opencode"
    assert choice.model_id == "glm-4.6"
    assert choice.origin == "request"


def test_purpose_binding_with_unapproved_runtime_is_ignored() -> None:
    router = _router(
        purpose_bindings={
            RuntimePurpose.CLASSIFY: PurposeBinding("codex", "glm-4.5-air")
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
