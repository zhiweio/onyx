"""Operator-configured hosts that may resolve to a private address.

Local SearXNG, Firecrawl, and similar search/crawler services run on Docker
or the host. They are not vendor MCP allowlist entries.
"""

from __future__ import annotations


def _lower_hosts(hosts: set[str]) -> set[str]:
    return {item.lower() for item in hosts}


def trusted_infra_hosts() -> set[str]:
    from onyx.configs.app_configs import (
        MCP_GATEWAY_TRUSTED_HOSTS,
        WEB_SEARCH_SERVICE_HOSTS,
    )

    return _lower_hosts(MCP_GATEWAY_TRUSTED_HOSTS) | _lower_hosts(
        WEB_SEARCH_SERVICE_HOSTS
    )


def is_trusted_infra_host(host: str) -> bool:
    return bool(host) and host.lower() in trusted_infra_hosts()


def is_web_search_service_host(host: str) -> bool:
    from onyx.configs.app_configs import WEB_SEARCH_SERVICE_HOSTS

    return bool(host) and host.lower() in _lower_hosts(WEB_SEARCH_SERVICE_HOSTS)
