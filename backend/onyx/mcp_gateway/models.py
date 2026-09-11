from dataclasses import dataclass, field, replace
from typing import Any

from onyx.configs.app_configs import (
    MCP_RESULT_DIGEST_MAX_BYTES,
    MCP_RESULT_INLINE_THRESHOLD_BYTES,
    MCP_RESULT_MAX_BYTES,
)
from onyx.db.enums import (
    MCPGatewayAuthAdapter,
    MCPGatewayCallOutcome,
    MCPGatewayRefreshMode,
    MCPResultStorage,
    MCPTransport,
)


@dataclass(frozen=True)
class CachePolicySpec:
    """How one tool's results are cached, stored, and summarized.

    Resolved per call by layering, most specific first: a DB policy row, the
    catalog entry's `policy_overrides`, the provider pack's per-tool policy,
    then the pack default.
    """

    refresh_mode: MCPGatewayRefreshMode = MCPGatewayRefreshMode.SWR
    ttl_seconds: int = 86400
    swr_seconds: int = 86400
    schedule_cron: str | None = None
    key_fields: list[str] | None = None
    normalize: dict[str, Any] | None = None
    cache_empty_ttl_seconds: int = 3600

    # Storage tiering. A result at or below inline_threshold_bytes is kept in
    # Postgres; a larger one goes to the file store. Past max_response_bytes
    # nothing is persisted and the call is passed through.
    inline_threshold_bytes: int = MCP_RESULT_INLINE_THRESHOLD_BYTES
    max_response_bytes: int = MCP_RESULT_MAX_BYTES

    # Ops digest stored with the blob. Not sent to the model.
    digest_max_bytes: int = MCP_RESULT_DIGEST_MAX_BYTES
    # Dotted paths pulled out of the payload for the ops digest, e.g.
    # "structuredContent.company.name".
    digest_paths: tuple[str, ...] = ()

    tool_globs: tuple[str, ...] = ()


_POLICY_FIELDS = frozenset(
    {
        "refresh_mode",
        "ttl_seconds",
        "swr_seconds",
        "schedule_cron",
        "key_fields",
        "normalize",
        "cache_empty_ttl_seconds",
        "inline_threshold_bytes",
        "max_response_bytes",
        "digest_max_bytes",
        "digest_paths",
        "tool_globs",
    }
)


def policy_from_mapping(
    raw: dict[str, Any], base: CachePolicySpec | None = None
) -> CachePolicySpec:
    """Overlay an admin-supplied dict onto a base policy.

    Unknown keys are ignored so a catalog entry written against a newer schema
    does not break an older deployment.
    """
    spec = base or CachePolicySpec()
    updates: dict[str, Any] = {}
    for key, value in raw.items():
        if key not in _POLICY_FIELDS:
            continue
        if key == "refresh_mode":
            updates[key] = MCPGatewayRefreshMode(value)
        elif key in ("digest_paths", "tool_globs"):
            updates[key] = tuple(value) if isinstance(value, (list, tuple)) else ()
        else:
            updates[key] = value
    return replace(spec, **updates)


@dataclass(frozen=True)
class PackEndpoint:
    """One upstream URL inside a multi-server provider family."""

    slug: str
    display_name: str
    upstream_url: str
    description: str = ""


@dataclass(frozen=True)
class ProviderPack:
    """Defaults for one upstream MCP product.

    A pack is data, not behavior: it seeds sensible cache policies so an admin
    installing a known provider does not start from nothing. Every field can be
    overridden per catalog entry, and `generic_http` covers anything unknown.

    Families (HiThink, Qichacha, Zhihuiya) list every HTTP endpoint in
    ``endpoints``. A pack with no endpoints still uses ``default_upstream_url``.
    """

    slug: str
    display_name: str
    default_upstream_url: str = ""
    description: str = ""
    # common | enterprise | generic — used only by the mcp-actions pack picker
    group: str = "generic"
    transport: MCPTransport = MCPTransport.STREAMABLE_HTTP
    auth_adapter: MCPGatewayAuthAdapter = MCPGatewayAuthAdapter.BEARER
    # HEADER_MAP only: header the admin API key is copied into.
    auth_header_name: str | None = None
    default_policy: CachePolicySpec = field(default_factory=CachePolicySpec)
    tool_policies: tuple[CachePolicySpec, ...] = ()
    # Providers that tunnel every call through one entry tool, e.g.
    # call_tool(name=..., arguments=...). The gateway unwraps these so the
    # cache key names the real tool.
    nested_entry_tools: tuple[str, ...] = ()
    batch_entry_tools: tuple[str, ...] = ()
    endpoints: tuple[PackEndpoint, ...] = ()

    def resolved_endpoints(self) -> tuple[PackEndpoint, ...]:
        if self.endpoints:
            return self.endpoints
        if self.default_upstream_url:
            return (
                PackEndpoint(
                    slug=self.slug,
                    display_name=self.display_name,
                    upstream_url=self.default_upstream_url,
                    description=self.description,
                ),
            )
        return ()


@dataclass
class StoredResult:
    """A persisted MCP result: metadata plus the body, if it was loaded."""

    blob_id: str
    content_hash: str
    size_bytes: int
    storage: MCPResultStorage
    digest: dict[str, Any]
    file_id: str | None = None
    payload: dict[str, Any] | None = None

    @property
    def is_large(self) -> bool:
        return self.storage == MCPResultStorage.OBJECT


@dataclass
class ResolvedCall:
    tool_name: str
    effective_tool_name: str
    arguments: dict[str, Any]
    cache_key: str
    policy: CachePolicySpec
    outcome: MCPGatewayCallOutcome
    result: dict[str, Any]
    upstream_billed: bool
    latency_ms: int
    stored: StoredResult | None = None
    error_message: str | None = None
