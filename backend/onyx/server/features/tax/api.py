from fastapi import APIRouter, Depends
from pydantic import BaseModel

from onyx.auth.permissions import require_permission
from onyx.db.enums import Permission
from onyx.db.models import User
from onyx.tax.models import PluginStatus
from onyx.tax.registry import get_plugins

router = APIRouter(prefix="/tax")


class TaxPluginHealth(BaseModel):
    source_id: str
    display_name: str
    domain: str
    trust_tier: str
    access_mode: str
    status: PluginStatus


class TaxPluginHealthResponse(BaseModel):
    plugins: list[TaxPluginHealth]


@router.get("/plugins")
def list_tax_plugins(
    _: User = Depends(require_permission(Permission.BASIC_ACCESS)),
) -> TaxPluginHealthResponse:
    plugins = []
    for plugin in get_plugins():
        plugins.append(
            TaxPluginHealth(
                source_id=plugin.source_id,
                display_name=plugin.display_name,
                domain=plugin.domain.value,
                trust_tier=plugin.trust_tier.value,
                access_mode=plugin.access_mode.value,
                status=plugin.healthcheck(),
            )
        )
    return TaxPluginHealthResponse(plugins=plugins)
