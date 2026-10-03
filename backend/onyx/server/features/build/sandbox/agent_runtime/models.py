"""Agent model registry: gateway-catalog snapshot + runtime support matrix.

The model set is a snapshot of the Onyx gateway catalog, which is built
from the admin-configured LLM providers (the "Model Providers" tab) —
the single source of truth shared with the sandbox serving path
(``build_onyx_gateway_config``). The snapshot is refreshed by the admin
listing endpoint (``registry_api.list_agent_models``) and consulted by
the ``HarnessRouter``.

Runtime support matrix and probe/fingerprint helpers keep the QM-ported
semantics:

- Each snapshot entry declares which agent runtimes can drive it, keyed
  off the provider type (codex speaks the OpenAI-completions protocol,
  so anthropic-provider models are opencode-only).
- ``fingerprint`` returns an HMAC over the canonical spec plus a
  credential revision, so a stored "verified" attestation dies when the
  spec or the credential changes.
- ``classify_provider_error`` maps provider exceptions to stable failure
  codes for probe reporting.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Any, Iterable, Protocol

from onyx.utils.logger import setup_logger

logger = setup_logger()

# Registries allowed to drive each entry. "opencode" is the primary
# runtime; codex declares support only where its protocol (OpenAI
# chat-completions) carries the provider cleanly.
_RUNTIME_OPENCODE = frozenset({"opencode"})
_RUNTIME_OPENAI_COMPAT = frozenset({"opencode", "codex"})

_ANTHROPIC_PROVIDER = "anthropic"


@dataclass(frozen=True)
class AgentModelSpec:
    """One driveable model, derived from a gateway catalog entry."""

    model_id: str
    provider: str
    display_name: str
    context_window: int | None
    max_output_tokens: int | None
    runtimes: frozenset[str]
    is_default: bool = False
    notes: str = ""


class CatalogEntry(Protocol):
    """Structural view of a gateway model descriptor.

    ``GatewayModelDescriptor`` satisfies this without an import, keeping
    the registry core decoupled from the gateway module.
    """

    @property
    def id(self) -> str: ...

    @property
    def provider(self) -> str: ...

    @property
    def display_name(self) -> str: ...

    @property
    def max_input_tokens(self) -> int | None: ...

    @property
    def max_output_tokens(self) -> int | None: ...


def _runtimes_for_provider(provider: str) -> frozenset[str]:
    # codex speaks the OpenAI-completions protocol; anthropic-provider
    # models answer the anthropic-messages surface, which only opencode
    # carries today.
    if provider == _ANTHROPIC_PROVIDER:
        return _RUNTIME_OPENCODE
    return _RUNTIME_OPENAI_COMPAT


def _spec_from_catalog_entry(entry: CatalogEntry) -> AgentModelSpec:
    return AgentModelSpec(
        model_id=entry.id,
        provider=entry.provider,
        display_name=entry.display_name,
        context_window=entry.max_input_tokens,
        max_output_tokens=entry.max_output_tokens,
        runtimes=_runtimes_for_provider(entry.provider),
    )


# Admin-facing snapshot applied at runtime (after each registry listing).
# Kept as a flat index so every lookup (router support matrix, default
# resolution, fingerprinting) is catalog-aware without threading state.
_MODEL_INDEX: dict[str, AgentModelSpec] = {}


def apply_model_catalog_cache(
    entries: Iterable[CatalogEntry],
    default_model_id: str | None,
) -> None:
    """Refresh the registry snapshot from gateway catalog entries."""
    global _MODEL_INDEX
    index = {entry.id: _spec_from_catalog_entry(entry) for entry in entries}
    if default_model_id is not None and default_model_id in index:
        default_spec = index[default_model_id]
        index[default_model_id] = AgentModelSpec(
            model_id=default_spec.model_id,
            provider=default_spec.provider,
            display_name=default_spec.display_name,
            context_window=default_spec.context_window,
            max_output_tokens=default_spec.max_output_tokens,
            runtimes=default_spec.runtimes,
            is_default=True,
        )
    _MODEL_INDEX = index


def iter_models() -> tuple[AgentModelSpec, ...]:
    """The current snapshot, in catalog order."""
    return tuple(_MODEL_INDEX.values())


def get_model_spec(model_id: str) -> AgentModelSpec | None:
    """Look up one model; None when unknown."""
    return _MODEL_INDEX.get(model_id)


def model_supported_by(model_id: str, runtime_id: str) -> bool:
    """Whether ``runtime_id`` can drive ``model_id``."""
    spec = get_model_spec(model_id)
    return spec is not None and runtime_id in spec.runtimes


def default_model_for(runtime_id: str) -> str | None:
    """The snapshot default model that ``runtime_id`` can drive."""
    for spec in _MODEL_INDEX.values():
        if spec.is_default and runtime_id in spec.runtimes:
            return spec.model_id
    for spec in _MODEL_INDEX.values():
        if runtime_id in spec.runtimes:
            return spec.model_id
    return None


def _canonical_spec(spec: AgentModelSpec) -> str:
    return json.dumps(
        {
            "model_id": spec.model_id,
            "provider": spec.provider,
            "context_window": spec.context_window,
            "max_output_tokens": spec.max_output_tokens,
            "runtimes": sorted(spec.runtimes),
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def fingerprint(
    model_id: str,
    credential_revision: str,
    *,
    gateway_route: str = "",
    secret: bytes | None = None,
) -> str | None:
    """HMAC fingerprint binding a model spec to its credential and gateway.

    A stored attestation computed with a different ``credential_revision``
    or ``gateway_route`` no longer matches, forcing re-verification — the
    same invalidation QM's verifier guarantees.
    """
    spec = get_model_spec(model_id)
    if spec is None:
        return None
    material = "\n".join(
        (
            "onyx-agent-model-v1",
            _canonical_spec(spec),
            f"credential_revision={credential_revision}",
            f"gateway_route={gateway_route}",
        )
    ).encode("utf-8")
    if secret is None:
        secret = _default_secret()
    return hmac.new(secret, material, hashlib.sha256).hexdigest()


def _default_secret() -> bytes:
    """Derive a process-stable HMAC secret from the configured secret key.

    Falls back to a derived constant in tests where no secret is configured;
    fingerprints stay comparable within one process either way.
    """
    try:
        # CE equivalent of the upstream EE SECRET_KEY.
        from onyx.configs.app_configs import USER_AUTH_SECRET

        if USER_AUTH_SECRET:
            return hashlib.sha256(USER_AUTH_SECRET.encode("utf-8")).digest()
    except Exception:
        pass
    return hashlib.sha256(b"onyx-agent-model-registry-dev").digest()


# ── Probe failure classification (QM model-verification.ts port) ──────────

PROBE_FAILURE_TIMEOUT = "timeout"
PROBE_FAILURE_ACCESS_DENIED = "access_denied"
PROBE_FAILURE_QUOTA = "quota_or_rate_limit"
PROBE_FAILURE_MODEL_UNAVAILABLE = "model_unavailable"
PROBE_FAILURE_PROVIDER = "provider_failure"
PROBE_FAILURE_MISSING_CREDENTIAL = "missing_credential"
PROBE_FAILURE_UNKNOWN_MODEL = "unknown_model"

ProbeFailureCode = str


def classify_provider_error(exc: BaseException) -> ProbeFailureCode:
    """Map a provider exception to a stable failure code for reporting."""
    text = f"{type(exc).__name__}: {exc}".lower()
    if isinstance(exc, TimeoutError) or "timeout" in text or "timed out" in text:
        return PROBE_FAILURE_TIMEOUT
    if "401" in text or "unauthorized" in text or "invalid api key" in text:
        return PROBE_FAILURE_ACCESS_DENIED
    if "403" in text or "forbidden" in text:
        return PROBE_FAILURE_ACCESS_DENIED
    if "429" in text or "rate limit" in text or "quota" in text:
        return PROBE_FAILURE_QUOTA
    if "404" in text or "not found" in text or "does not exist" in text:
        return PROBE_FAILURE_MODEL_UNAVAILABLE
    if "no api key" in text or "missing credential" in text:
        return PROBE_FAILURE_MISSING_CREDENTIAL
    return PROBE_FAILURE_PROVIDER


def probe_model(
    model_id: str,
    complete: Any,
) -> tuple[bool, ProbeFailureCode | None]:
    """Run one real one-shot completion through ``complete``.

    ``complete`` must accept no arguments and return the assistant text
    (raising on failure). Kept as a callable so tests inject a fake and the
    real binding wraps the configured LLM stack.
    """
    spec = get_model_spec(model_id)
    if spec is None:
        return False, PROBE_FAILURE_UNKNOWN_MODEL
    try:
        reply = complete()
    except Exception as exc:
        logger.warning("Model probe failed for %s: %s", model_id, exc)
        return False, classify_provider_error(exc)
    text = reply if isinstance(reply, str) else str(reply)
    if not text.strip():
        return False, PROBE_FAILURE_PROVIDER
    return True, None
