from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from onyx.db.enums import MCPGatewayRefreshMode
from onyx.mcp_gateway.models import CachePolicySpec
from onyx.mcp_gateway.policy import effective_policies, freshness, resolve_policy
from onyx.mcp_gateway.registry import get_pack, policy_for_tool


def _entry(*, age_seconds: int, is_empty: bool = False) -> SimpleNamespace:
    now = datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc)
    return SimpleNamespace(
        last_fetched_at=now - timedelta(seconds=age_seconds),
        is_empty=is_empty,
    )


def test_patsnap_search_is_swr_and_eureka_is_bypass() -> None:
    pack = get_pack("patsnap")
    search = policy_for_tool(pack, "searchPatents")
    assert search.refresh_mode == MCPGatewayRefreshMode.SWR
    assert search.ttl_seconds == 86400
    eureka = policy_for_tool(pack, "eurekaAnalyze")
    assert eureka.refresh_mode == MCPGatewayRefreshMode.BYPASS


def test_qixinbao_enterprise_ttl() -> None:
    pack = get_pack("qixinbao")
    spec = policy_for_tool(pack, "getEnterpriseInfo")
    assert spec.refresh_mode == MCPGatewayRefreshMode.SWR
    assert spec.ttl_seconds == 7 * 86400


def test_tianyancha_risk_and_finance() -> None:
    pack = get_pack("tianyancha")
    risk = policy_for_tool(pack, "getCompanyRisk")
    assert risk.ttl_seconds == 12 * 3600
    finance = policy_for_tool(pack, "financialReport")
    assert finance.refresh_mode == MCPGatewayRefreshMode.TTL_AND_SCHEDULE
    assert finance.schedule_cron is not None


def test_unknown_pack_falls_back_to_generic() -> None:
    assert get_pack("does-not-exist").slug == "generic_http"
    assert get_pack(None).slug == "generic_http"


def test_fresh_stale_expired_and_bypass() -> None:
    now = datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc)
    ttl = CachePolicySpec(
        refresh_mode=MCPGatewayRefreshMode.TTL, ttl_seconds=60, swr_seconds=0
    )
    swr = CachePolicySpec(
        refresh_mode=MCPGatewayRefreshMode.SWR, ttl_seconds=60, swr_seconds=120
    )
    assert freshness(_entry(age_seconds=10), ttl, now) == "fresh"
    assert freshness(_entry(age_seconds=90), ttl, now) == "expired"
    assert freshness(_entry(age_seconds=90), swr, now) == "stale"
    assert freshness(_entry(age_seconds=200), swr, now) == "expired"
    assert (
        freshness(
            _entry(age_seconds=1),
            CachePolicySpec(refresh_mode=MCPGatewayRefreshMode.BYPASS),
            now,
        )
        == "expired"
    )
    assert (
        freshness(
            _entry(age_seconds=10_000),
            CachePolicySpec(refresh_mode=MCPGatewayRefreshMode.NEVER),
            now,
        )
        == "fresh"
    )


def test_empty_uses_short_ttl() -> None:
    now = datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc)
    policy = CachePolicySpec(
        refresh_mode=MCPGatewayRefreshMode.TTL,
        ttl_seconds=86400,
        cache_empty_ttl_seconds=30,
    )
    assert freshness(_entry(age_seconds=10, is_empty=True), policy, now) == "fresh"
    assert freshness(_entry(age_seconds=40, is_empty=True), policy, now) == "expired"


def test_schedule_due_is_expired() -> None:
    last = datetime(2026, 8, 28, 3, 0, tzinfo=timezone.utc)
    now = datetime(2026, 8, 30, 4, 0, tzinfo=timezone.utc)
    entry = SimpleNamespace(last_fetched_at=last, is_empty=False)
    policy = CachePolicySpec(
        refresh_mode=MCPGatewayRefreshMode.SCHEDULE,
        schedule_cron="0 3 * * *",
    )
    assert freshness(entry, policy, now) == "expired"


def test_nested_tool_resolves_to_inner_policy() -> None:
    _pack, effective, spec = resolve_policy(
        pack_slug="tianyancha",
        policy_overrides=None,
        tool_name="call_tool",
        arguments={"name": "getCompanyRisk", "arguments": {"id": "1"}},
    )
    assert effective == "getCompanyRisk"
    assert spec.refresh_mode == MCPGatewayRefreshMode.SWR
    assert spec.ttl_seconds == 12 * 3600


def test_catalog_override_wins_over_pack() -> None:
    _pack, effective, spec = resolve_policy(
        pack_slug="tianyancha",
        policy_overrides={"getCompanyRisk": {"refresh_mode": "bypass"}},
        tool_name="call_tool",
        arguments={"name": "getCompanyRisk", "arguments": {"id": "1"}},
    )
    assert effective == "getCompanyRisk"
    assert spec.refresh_mode == MCPGatewayRefreshMode.BYPASS


def test_override_is_layered_not_replacing() -> None:
    """A partial override keeps every field it does not mention."""
    _pack, _effective, spec = resolve_policy(
        pack_slug="tianyancha",
        policy_overrides={"getCompanyRisk": {"ttl_seconds": 99}},
        tool_name="getCompanyRisk",
        arguments={},
    )
    assert spec.ttl_seconds == 99
    assert spec.refresh_mode == MCPGatewayRefreshMode.SWR
    assert spec.swr_seconds == 86400


def test_glob_override_matches() -> None:
    _pack, _effective, spec = resolve_policy(
        pack_slug="generic_http",
        policy_overrides={"*search*": {"ttl_seconds": 7}},
        tool_name="companySearchV2",
        arguments={},
    )
    assert spec.ttl_seconds == 7


def test_entry_default_override_applies_to_unmatched_tools() -> None:
    _pack, _effective, spec = resolve_policy(
        pack_slug="generic_http",
        policy_overrides={"*": {"ttl_seconds": 11}},
        tool_name="anythingElse",
        arguments={},
    )
    assert spec.ttl_seconds == 11


def test_effective_policies_flags_overrides() -> None:
    rows = effective_policies("tianyancha", {"getCompanyRisk": {"ttl_seconds": 5}})
    by_label = {label: (spec, is_override) for label, spec, is_override in rows}
    assert by_label["*"][1] is False
    assert by_label["getCompanyRisk"][0].ttl_seconds == 5
    assert by_label["getCompanyRisk"][1] is True
