from typing import Protocol, runtime_checkable

from onyx.tax.models import (
    AccessMode,
    LiveQuery,
    NormalizedRecord,
    PluginStatus,
    SourceDomain,
    SourceHit,
    TrustTier,
)


@runtime_checkable
class LiveSourcePlugin(Protocol):
    source_id: str
    display_name: str
    domain: SourceDomain
    trust_tier: TrustTier
    access_mode: AccessMode

    def healthcheck(self) -> PluginStatus: ...

    def search(self, query: LiveQuery) -> list[SourceHit]: ...

    def fetch(self, hit: SourceHit) -> NormalizedRecord | None: ...
