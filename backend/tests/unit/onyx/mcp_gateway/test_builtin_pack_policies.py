from onyx.db.enums import MCPGatewayRefreshMode
from onyx.mcp_gateway.registry import get_pack, policy_for_tool


def test_generative_and_live_search_tools_bypass() -> None:
    deepwiki = get_pack("deepwiki")
    parallel = get_pack("parallel_search")
    assert policy_for_tool(deepwiki, "ask_question").refresh_mode == (
        MCPGatewayRefreshMode.BYPASS
    )
    assert policy_for_tool(parallel, "web_search").refresh_mode == (
        MCPGatewayRefreshMode.BYPASS
    )


def test_doc_tools_use_swr() -> None:
    context7 = get_pack("context7")
    deepwiki = get_pack("deepwiki")
    learn = get_pack("microsoft_learn")
    assert policy_for_tool(context7, "query-docs").refresh_mode == (
        MCPGatewayRefreshMode.SWR
    )
    assert policy_for_tool(deepwiki, "read_wiki_contents").refresh_mode == (
        MCPGatewayRefreshMode.SWR
    )
    assert policy_for_tool(learn, "microsoft_docs_fetch").refresh_mode == (
        MCPGatewayRefreshMode.SWR
    )
