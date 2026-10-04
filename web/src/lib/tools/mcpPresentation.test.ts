import { parseMcpToolName } from "@/lib/tools/mcpPresentation";

describe("parseMcpToolName", () => {
  it("splits the double-underscore convention", () => {
    expect(parseMcpToolName("mcp__deepwiki__ask_wiki_question")).toEqual({
      serverName: "deepwiki",
      toolName: "ask_wiki_question",
    });
  });

  it("splits the single-underscore convention on the first underscore", () => {
    expect(parseMcpToolName("mcp_deepwiki_ask_question")).toEqual({
      serverName: "deepwiki",
      toolName: "ask_question",
    });
  });

  it("returns no server for plain names", () => {
    expect(parseMcpToolName("rag_search")).toEqual({
      serverName: null,
      toolName: "rag_search",
    });
  });
});
