"""Admin API for the agent model registry: read-only sandbox view.

The list IS the Onyx gateway catalog: every visible model of every
accessible LLM provider (the "Model Providers" tab) — the same input the
sandbox serving path uses (``build_onyx_gateway_config``). One source,
two views; this endpoint only reshapes it for the admin table. The
in-process snapshot is kept warm by the startup + periodic registry
refresher (see ``models.refresh_model_catalog``), so this page no longer
carries that duty alone.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from onyx.auth.permissions import require_permission
from onyx.db.engine.sql_engine import get_session
from onyx.db.enums import Permission
from onyx.db.llm import fetch_all_accessible_llm_providers
from onyx.db.models import User
from onyx.server.features.build.sandbox.agent_runtime import models as model_registry
from onyx.server.gateway.model_catalog import build_gateway_model_catalog

router = APIRouter(prefix="/admin/agent-models")


@router.get("")
def list_agent_models(
    user: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),  # noqa: ARG001
    db_session: Session = Depends(get_session),
) -> dict[str, Any]:
    # The listing stays user-filtered (the admin's own view); the snapshot
    # refresh uses the deployment-wide superset so the runtime support
    # matrix and default marker don't depend on who opened the page last.
    model_registry.refresh_model_catalog(db_session)
    providers = fetch_all_accessible_llm_providers(db_session, user)
    catalog = build_gateway_model_catalog(providers)
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
        "catalog_size": len(catalog),
    }
