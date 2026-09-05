from urllib.parse import quote_plus

from onyx.tax.html_fetch import extract_anchors, fetch_html, fetch_title_and_text
from onyx.tax.models import (
    AccessMode,
    LiveQuery,
    NormalizedRecord,
    PluginStatus,
    SourceDomain,
    SourceHit,
    TrustTier,
)
from onyx.utils.logger import setup_logger

logger = setup_logger()


class HtmlSearchPlugin:
    """Live HTML search against an official site. Fail-open on network errors."""

    source_id: str
    display_name: str
    domain: SourceDomain
    trust_tier: TrustTier
    access_mode: AccessMode = AccessMode.HTML_SEARCH
    search_url_template: str
    allowed_hosts: tuple[str, ...]

    def healthcheck(self) -> PluginStatus:
        return PluginStatus(ok=True, configured=True)

    def search(self, query: LiveQuery) -> list[SourceHit]:
        url = self.search_url_template.format(query=quote_plus(query.query))
        try:
            html = fetch_html(url)
        except Exception:
            logger.warning(
                "HTML search failed for %s query=%s",
                self.source_id,
                query.query,
                exc_info=True,
            )
            return []
        hits: list[SourceHit] = []
        for href, title in extract_anchors(html, url):
            if not any(host in href for host in self.allowed_hosts):
                continue
            if href.rstrip("/") == url.rstrip("/"):
                continue
            hits.append(
                SourceHit(
                    source_id=self.source_id,
                    hit_id=href,
                    title=title[:240],
                    url=href,
                    snippet=title[:400],
                    score=1.0 - (len(hits) * 0.01),
                )
            )
            if len(hits) >= query.limit:
                break
        return hits

    def fetch(self, hit: SourceHit) -> NormalizedRecord | None:
        title = hit.title
        text = hit.snippet
        try:
            title, text = fetch_title_and_text(hit.url)
        except Exception:
            logger.debug("HTML fetch failed for %s", hit.url, exc_info=True)
        return NormalizedRecord(
            source_id=self.source_id,
            record_id=hit.hit_id,
            url=hit.url,
            title=title or hit.title,
            trust_tier=self.trust_tier,
            domain=self.domain,
            snippet=text[:600],
            full_text=text,
        )


class StaPolicyPlugin(HtmlSearchPlugin):
    source_id = "sta_policy"
    display_name = "国家税务总局政策法规"
    domain = SourceDomain.POLICY
    trust_tier = TrustTier.OFFICIAL
    search_url_template = "https://www.chinatax.gov.cn/s?wd={query}"
    allowed_hosts = ("chinatax.gov.cn",)


class StaViolationPlugin(HtmlSearchPlugin):
    source_id = "sta_violation"
    display_name = "重大税收违法案件"
    domain = SourceDomain.ENFORCEMENT
    trust_tier = TrustTier.OFFICIAL
    search_url_template = (
        "https://www.chinatax.gov.cn/chinatax/n810341/n810755/index.html?wd={query}"
    )
    allowed_hosts = ("chinatax.gov.cn",)


class TaxIntelPlugin(HtmlSearchPlugin):
    source_id = "tax_intel"
    display_name = "税务新闻与情报"
    domain = SourceDomain.NEWS
    trust_tier = TrustTier.NEWS
    search_url_template = "https://www.chinatax.gov.cn/s?wd={query}"
    allowed_hosts = ("chinatax.gov.cn",)
