from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from onyx.db.enums import MCPGatewayRefreshMode
from onyx.mcp_gateway.models import CachePolicySpec
from onyx.mcp_gateway.packs import policy_for_tool, get_pack
from onyx.mcp_gateway.policy import freshness, resolve_policy, spec_from_row


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


def test_resolve_pack_default_vs_db_override() -> None:
    db_row = SimpleNamespace(
        refresh_mode=MCPGatewayRefreshMode.BYPASS,
        ttl_seconds=0,
        swr_seconds=0,
        schedule_cron=None,
        key_fields=None,
        normalize=None,
        cache_empty_ttl_seconds=3600,
        max_response_bytes=2_000_000,
    )
    session = MagicMock()
    with patch("onyx.mcp_gateway.policy.get_policy", return_value=None):
        _pack, effective, spec = resolve_policy(
            session,
            provider_slug="tyc",
            pack_slug="tianyancha",
            tool_name="call_tool",
            arguments={"name": "getCompanyRisk", "arguments": {"id": "1"}},
        )
        assert effective == "getCompanyRisk"
        assert spec.refresh_mode == MCPGatewayRefreshMode.SWR
        assert spec.ttl_seconds == 12 * 3600

    with patch("onyx.mcp_gateway.policy.get_policy", return_value=db_row):
        _pack, effective, spec = resolve_policy(
            session,
            provider_slug="tyc",
            pack_slug="tianyancha",
            tool_name="call_tool",
            arguments={"name": "getCompanyRisk", "arguments": {"id": "1"}},
        )
        assert spec.refresh_mode == MCPGatewayRefreshMode.BYPASS
        assert spec_from_row(db_row).refresh_mode == MCPGatewayRefreshMode.BYPASS
