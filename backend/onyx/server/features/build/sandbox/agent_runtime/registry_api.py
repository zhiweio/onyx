"""Admin API for the agent model registry: read-only sandbox view.

The list IS the Onyx gateway catalog: every visible model of every
accessible LLM provider (the "Model Providers" tab) — the same input the
sandbox serving path uses (``build_onyx_gateway_config``). One source,
two views; this endpoint only reshapes it for the admin table and
refreshes the in-process registry snapshot.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from onyx.auth.permissions import require_permission
from onyx.db.engine.sql_engine import get_session
from onyx.db.enums import Permission
from onyx.db.llm import (
    fetch_all_accessible_llm_providers,
    fetch_default_craft_model,
    fetch_default_llm_model,
)
from onyx.db.models import User
from onyx.server.features.build.sandbox.agent_runtime import models as model_registry
from onyx.server.gateway.model_catalog import build_gateway_model_catalog

router = APIRouter(prefix="/admin/agent-models")


def _sandbox_default_model_id(db_session: Session, catalog_ids: set[str]) -> str | None:
    """Wire id of the effective sandbox default: craft default, else the
    chat default. Absent from the catalog (or unset) means no marker."""
    for model in (
        fetch_default_craft_model(db_session),
        fetch_default_llm_model(db_session),
    ):
        if model is None:
            continue
        candidate = f"{model.llm_provider_id}/{model.name}"
        if candidate in catalog_ids:
            return candidate
    return None


@router.get("")
def list_agent_models(
    user: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),  # noqa: ARG001
    db_session: Session = Depends(get_session),
) -> dict[str, Any]:
    providers = fetch_all_accessible_llm_providers(db_session, user)
    catalog = build_gateway_model_catalog(providers)
    default_model_id = _sandbox_default_model_id(
        db_session, {descriptor.id for descriptor in catalog}
    )
    model_registry.apply_model_catalog_cache(catalog, default_model_id)
    return {
        "models": [
            {
                "model_id": spec.model_id,
                "provider_id": int(spec.model_id.partition("/")[0]),
                "provider": spec.provider,
                "display_name": spec.display_name,
                "context_window": spec.context_window,
                "max_output_tokens": spec.max_output_tokens,
                "runtimes": sorted(spec.runtimes),
                "is_default": spec.is_default,
            }
            for spec in model_registry.iter_models()
        ],
    }
