"""Inject env API keys onto vendor CLI hosts.

HiThink, Qichacha, and Zhihuiya CLIs call vendor HTTPS hosts from the
sandbox. The keys stay on the API/proxy host. The image and the container
env never receive them.
"""

from __future__ import annotations

from dataclasses import dataclass

from mitmproxy import http

from onyx.configs.app_configs import (
    HITHINK_FINANCE_API_KEY,
    QCC_AGENT_API_KEY,
    ZHIHUIYA_MCP_API_KEY,
)
from onyx.sandbox_proxy.credential_injection import (
    CredentialResolver,
    CredentialUnavailableError,
    InjectionContext,
)
from onyx.utils.logger import setup_logger

logger = setup_logger()


@dataclass(frozen=True)
class _VendorHostRule:
    host: str
    header_name: str
    header_value: str


def _bearer(token: str) -> str:
    return f"Bearer {token}"


def vendor_cli_rules() -> tuple[_VendorHostRule, ...]:
    """Host rules that have a non-empty key. Empty keys stay unclaimed."""
    rules: list[_VendorHostRule] = []
    if HITHINK_FINANCE_API_KEY:
        rules.append(
            _VendorHostRule(
                host="fuyao.aicubes.cn",
                header_name="X-api-key",
                header_value=HITHINK_FINANCE_API_KEY,
            )
        )
    if ZHIHUIYA_MCP_API_KEY:
        rules.append(
            _VendorHostRule(
                host="connect.zhihuiya.com",
                header_name="Authorization",
                header_value=_bearer(ZHIHUIYA_MCP_API_KEY),
            )
        )
    if QCC_AGENT_API_KEY:
        rules.append(
            _VendorHostRule(
                host="agent.qcc.com",
                header_name="Authorization",
                header_value=_bearer(QCC_AGENT_API_KEY),
            )
        )
    return tuple(rules)


class BuiltinVendorCliResolver(CredentialResolver):
    """Injects built-in finance CLI keys on their vendor hosts."""

    def __init__(self, rules: tuple[_VendorHostRule, ...] | None = None) -> None:
        source = rules if rules is not None else vendor_cli_rules()
        self._rules = {rule.host: rule for rule in source}

    def claims(
        self,
        request: http.Request,
        ctx: InjectionContext,  # noqa: ARG002
    ) -> bool:
        return request.host.lower() in self._rules

    def resolve(
        self,
        request: http.Request,
        ctx: InjectionContext,  # noqa: ARG002
    ) -> dict[str, str]:
        rule = self._rules.get(request.host.lower())
        if rule is None:
            raise CredentialUnavailableError(
                f"vendor CLI host {request.host} has no configured key"
            )
        logger.debug("vendor_cli_resolver.injected host=%s", request.host)
        return {rule.header_name: rule.header_value}
