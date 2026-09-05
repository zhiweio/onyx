"""Module-level gating for the MCP Gateway.

The gateway is an optional building block. Three layers decide whether it is
usable, and every call site must go through this module rather than reading a
config value directly:

1. Deployment: ``MCP_GATEWAY_ENABLED`` decides whether the gateway process runs
   at all. An operator sets it; admins cannot change it from the UI.
2. Runtime: ``Settings.mcp_gateway_enabled`` is a KV-backed admin toggle. It
   flips without a restart.
3. Capability: ``is_gateway_enabled()`` is the conjunction of the two, and is
   what user-facing code checks.

When the gateway is off, system-scoped MCP servers disappear from every user
surface. User-scoped MCP servers are unaffected — they never route through the
gateway.
"""

from onyx.configs.app_configs import MCP_GATEWAY_ENABLED
from onyx.server.settings.store import load_settings
from onyx.utils.logger import setup_logger

logger = setup_logger()


def is_gateway_deployed() -> bool:
    """Whether the operator deployed the gateway process."""
    return MCP_GATEWAY_ENABLED


def is_gateway_enabled() -> bool:
    """Whether system-scoped MCP is usable right now.

    Fails closed: a KV read error disables the module rather than exposing
    system MCP servers whose access grants could not be confirmed.
    """
    if not MCP_GATEWAY_ENABLED:
        return False
    try:
        return load_settings(raise_on_error=True).mcp_gateway_enabled
    except Exception:
        logger.exception("Could not read MCP gateway setting; treating as disabled")
        return False
