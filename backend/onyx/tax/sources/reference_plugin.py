import json
from pathlib import Path

from onyx.tax.models import (
    AccessMode,
    LiveQuery,
    NormalizedRecord,
    PluginStatus,
    SourceDomain,
    SourceHit,
    TrustTier,
)

_REFERENCE_DIR = Path(__file__).resolve().parent.parent / "reference"


class TaxReferencePlugin:
    source_id = "tax_reference"
    display_name = "本地税务参考条目"
    domain = SourceDomain.REFERENCE
    trust_tier = TrustTier.PROFESSIONAL
    access_mode = AccessMode.LOCAL_FILE

    def healthcheck(self) -> PluginStatus:
        files = list(_REFERENCE_DIR.glob("*.json"))
        return PluginStatus(
            ok=bool(files),
            configured=True,
            message=f"{len(files)} reference files",
        )

    def _records(self) -> list[dict]:
        rows: list[dict] = []
        if not _REFERENCE_DIR.is_dir():
            return rows
        for path in _REFERENCE_DIR.glob("*.json"):
            payload = json.loads(path.read_text(encoding="utf-8"))
            rows.extend(payload.get("records") or [])
        return rows

    def search(self, query: LiveQuery) -> list[SourceHit]:
        needles = [part.lower() for part in query.query.split() if part]
        hits: list[SourceHit] = []
        for row in self._records():
            blob = " ".join(
                str(row.get(key) or "")
                for key in ("title", "snippet", "tax_type", "record_id")
            ).lower()
            if needles and not any(needle in blob for needle in needles):
                continue
            record_id = str(row.get("record_id") or "")
            hits.append(
                SourceHit(
                    source_id=self.source_id,
                    hit_id=record_id,
                    title=str(row.get("title") or record_id),
                    url=str(row.get("url") or ""),
                    snippet=str(row.get("snippet") or ""),
                    score=1.0,
                )
            )
            if len(hits) >= query.limit:
                break
        return hits

    def fetch(self, hit: SourceHit) -> NormalizedRecord | None:
        for row in self._records():
            if str(row.get("record_id")) == hit.hit_id:
                return NormalizedRecord(
                    source_id=self.source_id,
                    record_id=hit.hit_id,
                    url=str(row.get("url") or ""),
                    title=str(row.get("title") or hit.title),
                    trust_tier=self.trust_tier,
                    domain=self.domain,
                    tax_type=row.get("tax_type"),
                    region_code=row.get("region_code"),
                    issuing_body=row.get("issuing_body"),
                    snippet=str(row.get("snippet") or ""),
                    full_text=str(row.get("snippet") or ""),
                )
        return None
