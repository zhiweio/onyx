"""Registry of provider packs.

A pack carries the cache defaults for one upstream MCP product. Packs are
registered rather than hardcoded at the call site, so supporting a new provider
means dropping a data module into `packs/` — the engine does not change.

`GENERIC_HTTP_SLUG` is the fallback: an unknown provider still works, it just
starts from conservative defaults the admin can override per catalog entry.
"""

from fnmatch import fnmatch

from onyx.mcp_gateway.models import CachePolicySpec, ProviderPack
from onyx.mcp_gateway.packs import BUILTIN_PACKS
from onyx.utils.logger import setup_logger

logger = setup_logger()

GENERIC_HTTP_SLUG = "generic_http"

_PACKS: dict[str, ProviderPack] = {}


def register_pack(pack: ProviderPack) -> ProviderPack:
    """Add a pack to the registry. Re-registering a slug replaces it."""
    if pack.slug in _PACKS:
        logger.info("Replacing MCP gateway provider pack '%s'", pack.slug)
    _PACKS[pack.slug] = pack
    return pack


def get_pack(slug: str | None) -> ProviderPack:
    """Look up a pack, falling back to the generic one."""
    if slug and slug in _PACKS:
        return _PACKS[slug]
    return _PACKS[GENERIC_HTTP_SLUG]


def list_packs() -> list[ProviderPack]:
    """Packs in display order, generic first so it reads as the default."""
    by_name = sorted(_PACKS.values(), key=lambda pack: pack.display_name)
    return sorted(by_name, key=lambda pack: pack.slug != GENERIC_HTTP_SLUG)


def policy_for_tool(pack: ProviderPack, effective_tool_name: str) -> CachePolicySpec:
    """First pack policy whose globs match, else the pack default."""
    lowered = effective_tool_name.lower()
    for spec in pack.tool_policies:
        for glob in spec.tool_globs:
            if fnmatch(effective_tool_name, glob) or fnmatch(lowered, glob.lower()):
                return spec
    return pack.default_policy


for _pack in BUILTIN_PACKS:
    register_pack(_pack)
