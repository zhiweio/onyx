from onyx.mcp_gateway.keys import (
    batch_items,
    build_cache_key,
    canonicalize_arguments,
    expand_nested_tool,
)
from onyx.mcp_gateway.models import CachePolicySpec, ProviderPack
from onyx.mcp_gateway.packs.tianyancha import PACK as TIANYANCHA


def test_expand_nested_call_tool() -> None:
    name, args = expand_nested_tool(
        "call_tool",
        {"name": "getEnterpriseInfo", "arguments": {"keyword": " Acme  "}},
        TIANYANCHA,
    )
    assert name == "getEnterpriseInfo"
    assert args == {"keyword": " Acme  "}


def test_expand_leaves_plain_tool_unchanged() -> None:
    name, args = expand_nested_tool("hello", {"name": "Ada"}, None)
    assert name == "hello"
    assert args == {"name": "Ada"}


def test_canonicalize_sorts_and_drops_nulls() -> None:
    policy = CachePolicySpec()
    out = canonicalize_arguments({"b": 2, "a": 1, "empty": None}, policy)
    assert list(out.keys()) == ["a", "b"]


def test_canonicalize_key_fields_and_whitespace() -> None:
    policy = CachePolicySpec(
        key_fields=["keyword"],
        normalize={"keyword": {"collapse_ws": True, "lowercase": True}},
    )
    out = canonicalize_arguments({"keyword": "  Foo   Bar ", "pageSize": 20}, policy)
    assert out == {"keyword": "foo bar"}


def test_cache_key_includes_tenant() -> None:
    args = {"keyword": "acme"}
    left = build_cache_key(
        tenant_id="t1",
        provider_slug="patsnap",
        tool_name="search",
        effective_tool_name="search",
        canonical_args=args,
    )
    right = build_cache_key(
        tenant_id="t2",
        provider_slug="patsnap",
        tool_name="search",
        effective_tool_name="search",
        canonical_args=args,
    )
    assert left != right
    assert len(left) == 64


def test_batch_items_reads_tools_list() -> None:
    items = batch_items(
        {
            "tools": [
                {"name": "a", "arguments": {"x": 1}},
                {"name": "b", "args": {"y": 2}},
            ]
        }
    )
    assert len(items) == 2
    assert items[0]["name"] == "a"


def test_nested_pack_defaults() -> None:
    pack = ProviderPack(slug="x", display_name="x", default_upstream_url="")
    name, _args = expand_nested_tool("call_tools_batch", {"tools": []}, pack)
    assert name == "call_tools_batch"
