"""Agent model registry: mainland-first catalog + runtime support matrix.

QM reference: ``pi-models.ts`` / ``model-overlay.ts`` / ``model-verification.ts``.
Ported semantics:

- A static catalog of well-known China-provider models; each entry declares
  which agent runtimes can drive it.
- ``fingerprint`` returns an HMAC over the canonical spec plus a credential
  revision, so a stored "verified" attestation dies when the spec or the
  credential changes.
- ``classify_provider_error`` maps provider exceptions to stable failure
  codes for probe reporting.

Overlays (admin-defined models cloning a template) and DB persistence land
with the admin model-management page; this module is the resolution core.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass, field
from typing import Any

from onyx.utils.logger import setup_logger

logger = setup_logger()

# Registries allowed to drive each catalog entry. "opencode" is the primary
# runtime; codex/pi declare support only where their protocols carry the
# provider cleanly (OpenAI-compatible endpoints).
_RUNTIME_OPENCODE = frozenset({"opencode"})
_RUNTIME_OPENAI_COMPAT = frozenset({"opencode", "codex"})


@dataclass(frozen=True)
class AgentModelSpec:
    """One driveable model. Field set mirrors QM's ModelEntry (trimmed)."""

    model_id: str
    provider: str
    display_name: str
    context_window: int
    max_output_tokens: int
    runtimes: frozenset[str]
    is_default: bool = False
    notes: str = ""
    tags: frozenset[str] = field(default_factory=frozenset)


_CATALOG: tuple[AgentModelSpec, ...] = (    # ── Zhipu GLM (bigmodel) ─────────────────────────────────────────────
    AgentModelSpec(
        model_id="glm-4.7",
        provider="bigmodel",
        display_name="GLM-4.7",
        context_window=200_000,
        max_output_tokens=32_768,
        runtimes=_RUNTIME_OPENAI_COMPAT,
        is_default=True,
        notes="Primary general-purpose model for scenario work.",
        tags=frozenset({"chat", "reasoning"}),
    ),
    AgentModelSpec(
        model_id="glm-4.6",
        provider="bigmodel",
        display_name="GLM-4.6",
        context_window=200_000,
        max_output_tokens=32_768,
        runtimes=_RUNTIME_OPENAI_COMPAT,
        tags=frozenset({"chat"}),
    ),
    AgentModelSpec(
        model_id="glm-4.5-air",
        provider="bigmodel",
        display_name="GLM-4.5-Air",
        context_window=128_000,
        max_output_tokens=16_384,
        runtimes=_RUNTIME_OPENAI_COMPAT,
        tags=frozenset({"chat", "fast"}),
    ),
    # ── Alibaba Qwen (DashScope) ─────────────────────────────────────────
    AgentModelSpec(
        model_id="qwen3-max",
        provider="dashscope",
        display_name="Qwen3-Max",
        context_window=262_144,
        max_output_tokens=32_768,
        runtimes=_RUNTIME_OPENAI_COMPAT,
        tags=frozenset({"chat", "long-context"}),
    ),
    AgentModelSpec(
        model_id="qwen3-plus",
        provider="dashscope",
        display_name="Qwen3-Plus",
        context_window=131_072,
        max_output_tokens=16_384,
        runtimes=_RUNTIME_OPENAI_COMPAT,
        tags=frozenset({"chat"}),
    ),
    AgentModelSpec(
        model_id="qwen3-flash",
        provider="dashscope",
        display_name="Qwen3-Flash",
        context_window=131_072,
        max_output_tokens=16_384,
        runtimes=_RUNTIME_OPENAI_COMPAT,
        tags=frozenset({"chat", "fast"}),
    ),
    # ── DeepSeek ─────────────────────────────────────────────────────────
    AgentModelSpec(
        model_id="deepseek-chat",
        provider="deepseek",
        display_name="DeepSeek-V3 (chat)",
        context_window=131_072,
        max_output_tokens=16_384,
        runtimes=_RUNTIME_OPENAI_COMPAT,
        tags=frozenset({"chat", "code"}),
    ),
    AgentModelSpec(
        model_id="deepseek-reasoner",
        provider="deepseek",
        display_name="DeepSeek-R1 (reasoner)",
        context_window=131_072,
        max_output_tokens=32_768,
        runtimes=_RUNTIME_OPENAI_COMPAT,
        tags=frozenset({"reasoning"}),
    ),
)

_CATALOG_INDEX: dict[str, AgentModelSpec] = {spec.model_id: spec for spec in _CATALOG}

# Admin overlays applied at runtime (app start + after overlay CRUD).
# Kept as a flat index so every lookup (router support matrix, default
# resolution, fingerprinting) is overlay-aware without threading state.
_OVERLAY_INDEX: dict[str, AgentModelSpec] = {}


def apply_overlay_cache(rows: Any) -> None:
    """Refresh the overlay index from DB overlay rows (idempotent)."""
    global _OVERLAY_INDEX
    _OVERLAY_INDEX = {
        spec.model_id: spec for spec in merge_overlays(rows) if not spec.is_default
    }


def iter_models() -> tuple[AgentModelSpec, ...]:
    """The full static catalog, in declaration order."""
    return _CATALOG


def get_model_spec(model_id: str) -> AgentModelSpec | None:
    """Look up one model (catalog or overlay); None when unknown."""
    return _CATALOG_INDEX.get(model_id) or _OVERLAY_INDEX.get(model_id)


def model_supported_by(model_id: str, runtime_id: str) -> bool:
    """Whether ``runtime_id`` can drive ``model_id`` (catalog or overlay)."""
    spec = get_model_spec(model_id)
    return spec is not None and runtime_id in spec.runtimes


def default_model_for(runtime_id: str) -> str | None:
    """The catalog default model that ``runtime_id`` can drive."""
    for spec in _CATALOG:
        if spec.is_default and runtime_id in spec.runtimes:
            return spec.model_id
    for spec in _CATALOG:
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
    spec = _CATALOG_INDEX.get(model_id)
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
        from shared_configs.configs.base_configs import SECRET_KEY

        if SECRET_KEY:
            return hashlib.sha256(SECRET_KEY.encode("utf-8")).digest()
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
    spec = _CATALOG_INDEX.get(model_id)
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


# ── overlays (admin-defined clones over catalog templates) ────────────────


def overlay_spec(
    overlay_row: Any,
    *,
    template: AgentModelSpec | None = None,
) -> AgentModelSpec | None:
    """Merge a DB overlay row over its catalog template.

    Inherits context window / max output / runtimes from the template;
    explicit overlay values replace. Unknown templates are rejected
    (None) — an overlay cannot invent a provider the catalog lacks.
    """
    spec = template if template is not None else get_model_spec(overlay_row.template_model_id)
    if spec is None:
        return None
    return AgentModelSpec(
        model_id=overlay_row.model_id,
        provider=overlay_row.provider or spec.provider,
        display_name=overlay_row.name or spec.display_name,
        context_window=(
            overlay_row.context_window
            if overlay_row.context_window is not None
            else spec.context_window
        ),
        max_output_tokens=(
            overlay_row.max_output_tokens
            if overlay_row.max_output_tokens is not None
            else spec.max_output_tokens
        ),
        runtimes=spec.runtimes,
        is_default=False,
        notes=f"overlay of {spec.model_id}" + (
            f"; base_url={overlay_row.base_url}" if overlay_row.base_url else ""
        ),
        tags=spec.tags,
    )


def merge_overlays(
    overlay_rows: Any,
) -> list[AgentModelSpec]:
    """Effective catalog: static entries plus enabled overlays.

    An overlay whose model_id collides with a static entry wins (admins
    override defaults); overlays of unknown templates are skipped with
    a log line.
    """
    merged: dict[str, AgentModelSpec] = dict(_CATALOG_INDEX)
    defaults = {spec.model_id for spec in _CATALOG if spec.is_default}
    for row in overlay_rows:
        if not getattr(row, "enabled", True):
            continue
        spec = overlay_spec(row)
        if spec is None:
            logger.warning(
                "agent model overlay %s has unknown template %s",
                row.model_id,
                row.template_model_id,
            )
            continue
        if spec.model_id in defaults:
            logger.warning(
                "overlay %s collides with a default catalog model; skipped",
                spec.model_id,
            )
            continue
        merged[spec.model_id] = spec
    return list(merged.values())
