"""Unit tests for the agent model registry (catalog, matrix, fingerprint)."""

from onyx.server.features.build.sandbox.agent_runtime import models as reg


def test_catalog_contains_default_model() -> None:
    defaults = [spec for spec in reg.iter_models() if spec.is_default]
    assert len(defaults) == 1
    assert defaults[0].model_id == "glm-4.7"


def test_default_model_is_driveable_by_opencode() -> None:
    model_id = reg.default_model_for("opencode")
    assert model_id is not None
    assert reg.model_supported_by(model_id, "opencode")


def test_support_matrix() -> None:
    assert reg.model_supported_by("glm-4.7", "opencode")
    assert reg.model_supported_by("deepseek-chat", "codex")
    assert not reg.model_supported_by("glm-4.7", "pi")
    assert not reg.model_supported_by("missing-model", "opencode")


def test_unknown_model_has_no_default_and_no_fingerprint() -> None:
    assert reg.get_model_spec("missing-model") is None
    assert reg.default_model_for("pi") is None
    assert reg.fingerprint("missing-model", "rev1") is None


def test_fingerprint_changes_with_credential_revision_and_spec() -> None:
    base = reg.fingerprint("glm-4.7", "rev1", gateway_route="default")
    assert base is not None
    assert reg.fingerprint("glm-4.7", "rev1", gateway_route="default") == base
    # Credential change invalidates.
    assert reg.fingerprint("glm-4.7", "rev2", gateway_route="default") != base
    # Gateway change invalidates.
    assert reg.fingerprint("glm-4.7", "rev1", gateway_route="other") != base
    # Different model with same inputs produces a different fingerprint.
    assert reg.fingerprint("glm-4.6", "rev1", gateway_route="default") != base


def test_classify_provider_error_codes() -> None:
    import httpx

    assert reg.classify_provider_error(TimeoutError()) == reg.PROBE_FAILURE_TIMEOUT
    assert (
        reg.classify_provider_error(httpx.HTTPStatusError("401", request=None, response=None))
        == reg.PROBE_FAILURE_ACCESS_DENIED
    )
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
    ok, failure = reg.probe_model("glm-4.7", lambda: "OK")
    assert ok and failure is None

    ok, failure = reg.probe_model("glm-4.7", lambda: (_ for _ in ()).throw(RuntimeError("401")))
    assert not ok
    assert failure == reg.PROBE_FAILURE_ACCESS_DENIED

    ok, failure = reg.probe_model("missing-model", lambda: "OK")
    assert not ok and failure == reg.PROBE_FAILURE_UNKNOWN_MODEL

    ok, failure = reg.probe_model("glm-4.7", lambda: "   ")
    assert not ok and failure == reg.PROBE_FAILURE_PROVIDER
