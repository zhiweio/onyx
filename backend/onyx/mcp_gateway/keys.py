import hashlib
import json
import re
from typing import Any

from onyx.mcp_gateway.models import CachePolicySpec, ProviderPack

_WS = re.compile(r"\s+")

DEFAULT_NESTED_ENTRY_TOOLS = ("call_tool", "call_tools")
DEFAULT_BATCH_ENTRY_TOOLS = ("call_tools_batch",)


def expand_nested_tool(
    tool_name: str,
    arguments: dict[str, Any],
    pack: ProviderPack | None = None,
) -> tuple[str, dict[str, Any]]:
    """Return (effective_tool_name, args used for cache key / policy)."""
    nested = pack.nested_entry_tools if pack else DEFAULT_NESTED_ENTRY_TOOLS
    if tool_name in nested:
        inner_name = arguments.get("name") or arguments.get("tool")
        inner_args = arguments.get("arguments") or arguments.get("args") or {}
        if isinstance(inner_name, str) and inner_name:
            if isinstance(inner_args, dict):
                return inner_name, inner_args
            return inner_name, arguments
    return tool_name, arguments


def batch_items(arguments: dict[str, Any]) -> list[dict[str, Any]]:
    raw = arguments.get("tools") or arguments.get("calls") or arguments.get("items")
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    return []


def _normalize_value(value: Any, rules: dict[str, Any] | None, field: str) -> Any:
    if not isinstance(value, str):
        return value
    field_rules = (rules or {}).get(field) or (rules or {}).get("*") or {}
    if not isinstance(field_rules, dict):
        field_rules = {}
    text = value.strip()
    if field_rules.get("collapse_ws", True):
        text = _WS.sub(" ", text)
    if field_rules.get("lowercase"):
        text = text.lower()
    return text


def canonicalize_arguments(
    arguments: dict[str, Any],
    policy: CachePolicySpec,
) -> dict[str, Any]:
    selected: dict[str, Any]
    if policy.key_fields:
        selected = {
            key: arguments[key] for key in policy.key_fields if key in arguments
        }
    else:
        selected = dict(arguments)

    def walk(node: Any, field: str) -> Any:
        if node is None:
            return None
        if isinstance(node, dict):
            cleaned = {
                str(key): walk(value, str(key))
                for key, value in node.items()
                if value is not None
            }
            return {key: cleaned[key] for key in sorted(cleaned)}
        if isinstance(node, list):
            return [walk(item, field) for item in node]
        return _normalize_value(node, policy.normalize, field)

    walked = walk(selected, "")
    return walked if isinstance(walked, dict) else {"value": walked}


def build_cache_key(
    *,
    tenant_id: str,
    provider_slug: str,
    tool_name: str,
    effective_tool_name: str,
    canonical_args: dict[str, Any],
) -> str:
    payload = json.dumps(
        {
            "tenant_id": tenant_id,
            "provider_slug": provider_slug,
            "tool_name": tool_name,
            "effective_tool_name": effective_tool_name,
            "arguments": canonical_args,
        },
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
