"""Built-in provider packs.

Each module here is pure data: one `PACK` describing sensible cache defaults
for an upstream MCP product. To add a provider, drop a module in and list it
below — nothing in the engine changes.
"""

from onyx.mcp_gateway.models import ProviderPack
from onyx.mcp_gateway.packs import (
    context7,
    deepwiki,
    generic,
    microsoft_learn,
    parallel_search,
    patsnap,
    qixinbao,
    tianyancha,
)

BUILTIN_PACKS: tuple[ProviderPack, ...] = (
    deepwiki.PACK,
    context7.PACK,
    parallel_search.PACK,
    microsoft_learn.PACK,
    tianyancha.PACK,
    qixinbao.PACK,
    patsnap.PACK,
    generic.PACK,
)

__all__ = ["BUILTIN_PACKS"]
