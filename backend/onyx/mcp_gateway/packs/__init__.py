"""Built-in provider packs.

Each module here is pure data: one `PACK` describing sensible cache defaults
for an upstream MCP product. To add a provider, drop a module in and list it
below — nothing in the engine changes.
"""

from onyx.mcp_gateway.models import ProviderPack
from onyx.mcp_gateway.packs import generic, patsnap, qixinbao, tianyancha

BUILTIN_PACKS: tuple[ProviderPack, ...] = (
    generic.PACK,
    patsnap.PACK,
    qixinbao.PACK,
    tianyancha.PACK,
)

__all__ = ["BUILTIN_PACKS"]
