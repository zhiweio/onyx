"""Unit tests for `BuiltinVendorCliResolver`."""

from __future__ import annotations

from onyx.sandbox_proxy.credential_injection import InjectionContext
from onyx.sandbox_proxy.resolvers.vendor_cli import (
    BuiltinVendorCliResolver,
    _VendorHostRule,
)
from tests.unit.sandbox_proxy.conftest import make_flow, make_resolved_sandbox


def _ctx() -> InjectionContext:
    return InjectionContext(sandbox=make_resolved_sandbox(), matched_actions=None)


def _resolver() -> BuiltinVendorCliResolver:
    return BuiltinVendorCliResolver(
        rules=(
            _VendorHostRule(
                host="fuyao.aicubes.cn",
                header_name="X-api-key",
                header_value="hithink-key",
            ),
            _VendorHostRule(
                host="agent.qcc.com",
                header_name="Authorization",
                header_value="Bearer qcc-key",
            ),
            _VendorHostRule(
                host="connect.zhihuiya.com",
                header_name="Authorization",
                header_value="Bearer zhihuiya-key",
            ),
        )
    )


def test_claims_only_configured_vendor_hosts() -> None:
    resolver = _resolver()
    assert resolver.claims(make_flow(host="fuyao.aicubes.cn").request, _ctx())
    assert resolver.claims(make_flow(host="agent.qcc.com").request, _ctx())
    assert resolver.claims(make_flow(host="connect.zhihuiya.com").request, _ctx())
    assert not resolver.claims(make_flow(host="example.com").request, _ctx())


def test_injects_hithink_header_map() -> None:
    resolver = _resolver()
    headers = resolver.resolve(make_flow(host="fuyao.aicubes.cn").request, _ctx())
    assert headers == {"X-api-key": "hithink-key"}


def test_injects_qichacha_bearer() -> None:
    resolver = _resolver()
    headers = resolver.resolve(make_flow(host="agent.qcc.com").request, _ctx())
    assert headers == {"Authorization": "Bearer qcc-key"}


def test_empty_rules_claim_nothing() -> None:
    resolver = BuiltinVendorCliResolver(rules=())
    assert not resolver.claims(make_flow(host="fuyao.aicubes.cn").request, _ctx())
