from concurrent.futures import ThreadPoolExecutor, as_completed

from onyx.tax.cache import get_cached_records, set_cached_records
from onyx.tax.models import (
    AccessMode,
    LiveQuery,
    NormalizedRecord,
    OrchestratorResult,
    SourceDomain,
    SourceHit,
)
from onyx.tax.plugin import LiveSourcePlugin
from onyx.tax.registry import get_plugins
from onyx.utils.logger import setup_logger

logger = setup_logger()

_INTENT_DOMAINS: list[tuple[tuple[str, ...], SourceDomain]] = [
    (("专利", "patent", "ip"), SourceDomain.IP),
    (("企业", "信用", "司法", "裁判", "uscc", "company"), SourceDomain.COMMERCIAL),
    (("违法", "处罚", "案件", "稽查"), SourceDomain.ENFORCEMENT),
    (("新闻", "趋势", "情报"), SourceDomain.NEWS),
    (("政策", "法规", "公告", "税率", "增值税", "所得税"), SourceDomain.POLICY),
]


def _domains_for_query(query: LiveQuery) -> list[SourceDomain]:
    if query.domains:
        return query.domains
    blob = " ".join(
        part
        for part in (query.intent, query.query, query.patent_keyword, query.company)
        if part
    ).lower()
    matched = [
        domain
        for needles, domain in _INTENT_DOMAINS
        if any(needle in blob for needle in needles)
    ]
    if matched:
        return list(dict.fromkeys(matched))
    return [SourceDomain.POLICY, SourceDomain.REFERENCE]


def _select_plugins(query: LiveQuery) -> list[LiveSourcePlugin]:
    plugins = get_plugins()
    if query.source_ids:
        allowed = set(query.source_ids)
        return [plugin for plugin in plugins if plugin.source_id in allowed]
    domains = set(_domains_for_query(query))
    selected = [plugin for plugin in plugins if plugin.domain in domains]
    if SourceDomain.POLICY in domains:
        reference = next(
            (plugin for plugin in plugins if plugin.source_id == "tax_reference"),
            None,
        )
        if reference is not None and reference not in selected:
            selected.append(reference)
    return selected


def _run_plugin(
    plugin: LiveSourcePlugin, query: LiveQuery
) -> tuple[str, list[NormalizedRecord], str | None]:
    cache_q = f"{query.query}|{query.company or ''}|{query.uscc or ''}"
    use_local_cache = plugin.access_mode != AccessMode.MCP
    if use_local_cache:
        cached = get_cached_records(plugin.source_id, cache_q)
        if cached is not None:
            return plugin.source_id, cached, None
    try:
        hits: list[SourceHit] = plugin.search(query)
    except Exception as exc:
        logger.warning("Plugin %s search failed", plugin.source_id, exc_info=True)
        return plugin.source_id, [], f"{plugin.source_id}: search failed ({exc})"
    records: list[NormalizedRecord] = []
    for hit in hits:
        try:
            record = plugin.fetch(hit)
        except Exception:
            logger.debug(
                "Plugin %s fetch failed for %s",
                plugin.source_id,
                hit.hit_id,
                exc_info=True,
            )
            continue
        if record is not None:
            records.append(record)
    if use_local_cache:
        set_cached_records(plugin.source_id, cache_q, records)
    return plugin.source_id, records, None


def _dedupe(records: list[NormalizedRecord]) -> list[NormalizedRecord]:
    seen: set[str] = set()
    out: list[NormalizedRecord] = []
    for record in records:
        key = record.url or f"{record.source_id}:{record.record_id}"
        if key in seen:
            continue
        seen.add(key)
        out.append(record)
    return out


def run_live_query(query: LiveQuery) -> OrchestratorResult:
    plugins = _select_plugins(query)
    notes: list[str] = []
    records: list[NormalizedRecord] = []
    if not plugins:
        return OrchestratorResult(
            records=[], plugin_notes=["No tax plugins matched this query."]
        )
    with ThreadPoolExecutor(max_workers=min(6, len(plugins))) as pool:
        futures = [pool.submit(_run_plugin, plugin, query) for plugin in plugins]
        for future in as_completed(futures):
            source_id, plugin_records, note = future.result()
            records.extend(plugin_records)
            if note:
                notes.append(note)
            elif not plugin_records:
                plugin = next(p for p in plugins if p.source_id == source_id)
                status = plugin.healthcheck()
                if not status.configured:
                    notes.append(f"{source_id}: {status.message}")
    return OrchestratorResult(records=_dedupe(records), plugin_notes=notes)
