"""Entry point for the commercial MCP gateway process."""

import uvicorn

from onyx.configs.app_configs import (
    MCP_GATEWAY_ENABLED,
    MCP_GATEWAY_HOST,
    MCP_GATEWAY_PORT,
)
from onyx.tracing.setup import setup_tracing
from onyx.utils.logger import setup_logger
from onyx.utils.variable_functionality import set_is_ee_based_on_env_variable

logger = setup_logger()


def main() -> None:
    if not MCP_GATEWAY_ENABLED:
        logger.info("MCP gateway is disabled (MCP_GATEWAY_ENABLED=false)")
        return

    set_is_ee_based_on_env_variable()
    setup_tracing()
    logger.info("Starting MCP gateway on %s:%s", MCP_GATEWAY_HOST, MCP_GATEWAY_PORT)

    from onyx.mcp_gateway.api import mcp_gateway_app

    uvicorn.run(
        mcp_gateway_app,
        host=MCP_GATEWAY_HOST,
        port=MCP_GATEWAY_PORT,
        log_config=None,
    )


if __name__ == "__main__":
    main()
