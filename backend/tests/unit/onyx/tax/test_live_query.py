from onyx.tax.models import (
    AccessMode,
    LiveQuery,
    NormalizedRecord,
    PluginStatus,
    SourceDomain,
    SourceHit,
    TrustTier,
)
from onyx.tax.orchestrator import run_live_query
from onyx.tax.registry import get_plugins, set_plugins_for_tests
from onyx.tax.sources.reference_plugin import TaxReferencePlugin


class _FakePlugin:
    source_id = "fake_policy"
    display_name = "Fake"
    domain = SourceDomain.POLICY
    trust_tier = TrustTier.OFFICIAL
    access_mode = AccessMode.LOCAL_FILE

    def healthcheck(self) -> PluginStatus:
        return PluginStatus(ok=True, configured=True)

    def search(self, query: LiveQuery) -> list[SourceHit]:
        return [
            SourceHit(
                source_id=self.source_id,
                hit_id="a",
                title="Policy A",
                url="https://example.com/a",
                snippet="vat 13%",
            ),
            SourceHit(
                source_id=self.source_id,
                hit_id="b",
                title="Policy A copy",
                url="https://example.com/a",
                snippet="dup",
            ),
        ]

    def fetch(self, hit: SourceHit) -> NormalizedRecord:
        return NormalizedRecord(
            source_id=self.source_id,
            record_id=hit.hit_id,
            url=hit.url,
            title=hit.title,
            trust_tier=self.trust_tier,
            domain=self.domain,
            snippet=hit.snippet,
        )


class _UnconfiguredMcp:
    source_id = "qixinbao_mcp"
    display_name = "Qixinbao"
    domain = SourceDomain.COMMERCIAL
    trust_tier = TrustTier.COMMERCIAL
    access_mode = AccessMode.MCP

    def healthcheck(self) -> PluginStatus:
        return PluginStatus(
            ok=False, configured=False, message="No MCP server name matches 'qixinbao'."
        )

    def search(self, query: LiveQuery) -> list[SourceHit]:
        return []

    def fetch(self, hit: SourceHit) -> NormalizedRecord | None:
        return None


def test_registry_can_disable_and_override() -> None:
    try:
        set_plugins_for_tests([_FakePlugin()])
        assert [plugin.source_id for plugin in get_plugins()] == ["fake_policy"]
    finally:
        set_plugins_for_tests(None)


def test_orchestrator_dedupes_urls(monkeypatch) -> None:
    monkeypatch.setattr("onyx.tax.orchestrator.get_cached_records", lambda *_: None)
    monkeypatch.setattr("onyx.tax.orchestrator.set_cached_records", lambda *_: None)
    try:
        set_plugins_for_tests([_FakePlugin()])
        result = run_live_query(LiveQuery(query="增值税"))
        assert len(result.records) == 1
        assert result.records[0].url == "https://example.com/a"
    finally:
        set_plugins_for_tests(None)


def test_mcp_not_configured_is_noted(monkeypatch) -> None:
    monkeypatch.setattr("onyx.tax.orchestrator.get_cached_records", lambda *_: None)
    monkeypatch.setattr("onyx.tax.orchestrator.set_cached_records", lambda *_: None)
    try:
        set_plugins_for_tests([_UnconfiguredMcp()])
        result = run_live_query(
            LiveQuery(query="企业信用", source_ids=["qixinbao_mcp"])
        )
        assert result.records == []
        assert any("qixinbao" in note for note in result.plugin_notes)
    finally:
        set_plugins_for_tests(None)


def test_reference_plugin_matches_local_json() -> None:
    plugin = TaxReferencePlugin()
    hits = plugin.search(LiveQuery(query="增值税"))
    assert hits
    record = plugin.fetch(hits[0])
    assert record is not None
    assert record.tax_type == "VAT"
