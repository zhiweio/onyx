"""Admin API for the agent model registry: merged view, overlay CRUD, verify.

The merged view = static catalog + enabled overlays; verification runs
a real one-shot completion through the configured LLM stack and stores
the HMAC fingerprint attestation (spec + credential revision + gateway).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from onyx.auth.permissions import require_permission
from onyx.db.engine.sql_engine import get_session
from onyx.db.enums import Permission
from onyx.db.models import AgentModelOverlay, User
from onyx.error_handling.error_codes import OnyxErrorCode
from onyx.error_handling.exceptions import OnyxError
from onyx.server.features.build.sandbox.agent_runtime import models as model_registry

router = APIRouter(prefix="/admin/agent-models")


class OverlayCreateRequest(BaseModel):
    name: str
    provider: str
    template_model_id: str
    model_id: str | None = None  # defaults to name
    context_window: int | None = None
    max_output_tokens: int | None = None
    base_url: str | None = None
    enabled: bool = True


class OverlayUpdateRequest(BaseModel):
    name: str | None = None
    context_window: int | None = None
    max_output_tokens: int | None = None
    base_url: str | None = None
    enabled: bool | None = None


def _all_overlays(db_session: Session) -> list[AgentModelOverlay]:
    return list(db_session.scalars(select(AgentModelOverlay)))


def _serialize_spec(spec: model_registry.AgentModelSpec) -> dict[str, Any]:
    return {
        "model_id": spec.model_id,
        "provider": spec.provider,
        "display_name": spec.display_name,
        "context_window": spec.context_window,
        "max_output_tokens": spec.max_output_tokens,
        "runtimes": sorted(spec.runtimes),
        "is_default": spec.is_default,
        "notes": spec.notes,
    }


@router.get("")
def list_agent_models(
    user: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),  # noqa: ARG001
    db_session: Session = Depends(get_session),
) -> dict[str, Any]:
    overlays = list(db_session.scalars(select(AgentModelOverlay)))
    overlay_by_model = {row.model_id: row for row in overlays}
    merged = model_registry.merge_overlays(overlays)
    return {
        "models": [
            {
                **_serialize_spec(spec),
                "overlay": _serialize_overlay(overlay_by_model.get(spec.model_id)),
            }
            for spec in merged
        ],
    }


def _serialize_overlay(row: AgentModelOverlay | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "id": row.id,
        "name": row.name,
        "template_model_id": row.template_model_id,
        "base_url": row.base_url,
        "enabled": row.enabled,
        "verified_at": row.verified_at.isoformat() if row.verified_at else None,
        "verify_error": row.verify_error,
        "fingerprint": row.fingerprint,
    }


@router.post("")
def create_overlay(
    request: OverlayCreateRequest,
    user: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> dict[str, Any]:
    if model_registry.get_model_spec(request.template_model_id) is None:
        raise OnyxError(
            OnyxErrorCode.VALIDATION_ERROR,
            f"unknown template model {request.template_model_id!r}",
        )
    model_id = (request.model_id or request.name).strip().lower()
    clash = db_session.scalar(
        select(AgentModelOverlay.id).where(AgentModelOverlay.model_id == model_id)
    )
    if clash is not None:
        raise OnyxError(OnyxErrorCode.CONFLICT, f"overlay {model_id!r} already exists")
    row = AgentModelOverlay(
        name=request.name.strip(),
        provider=request.provider.strip(),
        template_model_id=request.template_model_id,
        model_id=model_id,
        context_window=request.context_window,
        max_output_tokens=request.max_output_tokens,
        base_url=request.base_url,
        enabled=request.enabled,
        created_by=user.id,
    )
    db_session.add(row)
    db_session.commit()
    model_registry.apply_overlay_cache(_all_overlays(db_session))
    return _serialize_overlay(row) or {}


@router.patch("/{overlay_id}")
def update_overlay(
    overlay_id: int,
    request: OverlayUpdateRequest,
    user: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),  # noqa: ARG001
    db_session: Session = Depends(get_session),
) -> dict[str, Any]:
    row = db_session.get(AgentModelOverlay, overlay_id)
    if row is None:
        raise OnyxError(OnyxErrorCode.NOT_FOUND, f"overlay {overlay_id} not found")
    if request.name is not None:
        row.name = request.name.strip()
    if request.context_window is not None:
        row.context_window = request.context_window
    if request.max_output_tokens is not None:
        row.max_output_tokens = request.max_output_tokens
    if request.base_url is not None:
        row.base_url = request.base_url
    if request.enabled is not None:
        row.enabled = request.enabled
    # spec changed: the old attestation no longer applies
    row.fingerprint = None
    row.verified_at = None
    db_session.commit()
    model_registry.apply_overlay_cache(_all_overlays(db_session))
    return _serialize_overlay(row) or {}


@router.delete("/{overlay_id}")
def delete_overlay(
    overlay_id: int,
    user: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),  # noqa: ARG001
    db_session: Session = Depends(get_session),
) -> dict[str, Any]:
    row = db_session.get(AgentModelOverlay, overlay_id)
    if row is None:
        raise OnyxError(OnyxErrorCode.NOT_FOUND, f"overlay {overlay_id} not found")
    db_session.delete(row)
    db_session.commit()
    model_registry.apply_overlay_cache(_all_overlays(db_session))
    return {"success": True}


@router.post("/{overlay_id}/verify")
def verify_overlay(
    overlay_id: int,
    _user: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Probe the overlay's provider with one real one-shot completion.

    The credential revision keys the fingerprint: a rotated key or an
    edited spec invalidates the stored attestation and forces
    re-verification.
    """
    row = db_session.get(AgentModelOverlay, overlay_id)
    if row is None:
        raise OnyxError(OnyxErrorCode.NOT_FOUND, f"overlay {overlay_id} not found")

    credential_revision = _provider_credential_revision(db_session, row.provider)

    def complete() -> str:
        return _run_probe_completion(row)

    ok, failure = model_registry.probe_model(row.template_model_id, complete)
    if ok:
        fingerprint = model_registry.fingerprint(
            row.model_id,
            credential_revision,
            gateway_route=row.base_url or "",
        )
        row.fingerprint = fingerprint
        row.verified_at = datetime.now(timezone.utc)
        row.verify_error = None
    else:
        row.fingerprint = None
        row.verified_at = None
        row.verify_error = failure
    db_session.commit()
    return _serialize_overlay(row) or {}


def _provider_credential_revision(db_session: Session, provider: str) -> str:
    """Cheap revision signal: provider name + its stored key hash prefix.

    Reads the deployment's LLM provider credential when present so a key
    rotation changes the revision (and thus invalidates fingerprints).
    """
    import hashlib

    from onyx.db.models import LLMProvider

    try:
        row = db_session.scalar(select(LLMProvider).where(LLMProvider.name == provider))
        if row is not None and row.api_key is not None:
            material = str(row.api_key._decrypt())  # decrypt-once for hashing
            digest = hashlib.sha256(material.encode()).hexdigest()[:12]
            return f"{provider}:{digest}"
    except Exception:
        pass
    return provider


def _run_probe_completion(_row: AgentModelOverlay) -> str:
    """One real completion through the configured LLM stack."""
    from onyx.llm.factory import get_default_llm
    from onyx.llm.models import UserMessage

    llm = get_default_llm()
    result = llm.invoke([UserMessage(content="Reply with the single word: OK")])
    content = getattr(result, "content", None)
    if isinstance(content, str) and content.strip():
        return content
    raise RuntimeError("provider returned an empty completion")
