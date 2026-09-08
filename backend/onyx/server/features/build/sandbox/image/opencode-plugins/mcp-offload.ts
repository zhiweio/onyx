// Writes large tool results (especially MCP) to disk and leaves a short
// digest in the model context. Craft has no history-fit path, so this is
// the only way a long job survives many MCP calls.

import type { Plugin } from "@opencode-ai/plugin";

const OFFLOAD_THRESHOLD = 4_000;
const PREVIEW_CHARS = 400;
const SKIP_TOOLS = new Set([
  "todowrite",
  "question",
  "connect_app",
  "webapp",
]);

function textFromOutput(output: {
  output?: unknown;
  content?: unknown;
}): string {
  const chunks: string[] = [];
  if (typeof output.output === "string" && output.output.length > 0) {
    chunks.push(output.output);
  }
  const content = output.content;
  if (Array.isArray(content)) {
    for (const part of content) {
      if (
        part &&
        typeof part === "object" &&
        "text" in part &&
        typeof (part as { text: unknown }).text === "string"
      ) {
        chunks.push((part as { text: string }).text);
      }
    }
  }
  return chunks.join("\n");
}

function safeName(raw: string): string {
  const cleaned = raw.replace(/[^a-zA-Z0-9._-]+/g, "_").slice(0, 80);
  return cleaned || "tool";
}

function rewriteSessionDeny(body: string): string | null {
  if (!/\/workspace\/sessions\//i.test(body)) return null;
  const denied =
    /denied|permission|forbidden|blocked|403/i.test(body);
  if (!denied) return null;
  return (
    "Stay in this session. Use relative outputs/. " +
    "Do not list /workspace/sessions."
  );
}

function rewriteWebfetchError(tool: string, body: string): string | null {
  if (tool !== "webfetch") return null;
  const blocked =
    /destination_blocked/i.test(body) ||
    /StatusCode:\s*non 2xx status code \(403/i.test(body) ||
    /Unable to fetch/i.test(body);
  if (!blocked) return null;
  const urlMatch = body.match(/https?:\/\/[^\s)"']+/);
  const url = urlMatch?.[0] ?? "";
  const host = (() => {
    try {
      return url ? new URL(url).hostname : "";
    } catch {
      return "";
    }
  })();
  return (
    `Web fetch returned HTTP 403 for ${url || "this URL"}. ` +
    `The sandbox proxy allows public scientific APIs; a 403 here is from ` +
    `the origin (bot filter, missing identifying User-Agent, or datacenter ` +
    `IP), not an internal-network deny.\n` +
    `Do not retry the same URL with bash. Use another tool this session already has, or webfetch on a fallback:\n` +
    `- PubMed: https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&retmode=json&term=QUERY\n` +
    `- Europe PMC: https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=QUERY&format=json\n` +
    (host.includes("fda.gov")
      ? `- openFDA: retry once with a simpler query (no extra quotes), format=text.\n`
      : "") +
    `Record the miss in outputs/exceptions and continue from sources you can fetch.`
  );
}

function digestText(body: string, tool: string): string {
  const preview = body.slice(0, PREVIEW_CHARS);
  return (
    `[Onyx MCP offload] ${tool} returned ${body.length} chars.\n\n` +
    `Preview:\n${preview}`
  );
}

export default (async ({ directory }) => {
  return {
    "tool.execute.after": async (input, output) => {
      if (!output) return;
      const tool =
        input && typeof input === "object" && "tool" in input
          ? String((input as { tool?: unknown }).tool ?? "tool")
          : "tool";
      if (SKIP_TOOLS.has(tool)) return;

      const body = textFromOutput(output);
      const sessionDeny = rewriteSessionDeny(body);
      if (sessionDeny) {
        output.output = sessionDeny;
        const content = (output as { content?: unknown }).content;
        if (Array.isArray(content)) {
          (output as { content: unknown[] }).content = [
            { type: "text", text: sessionDeny },
          ];
        }
        return;
      }
      const webfetchError = rewriteWebfetchError(tool, body);
      if (webfetchError) {
        output.output = webfetchError;
        const content = (output as { content?: unknown }).content;
        if (Array.isArray(content)) {
          (output as { content: unknown[] }).content = [
            { type: "text", text: webfetchError },
          ];
        }
        return;
      }
      if (body.length < OFFLOAD_THRESHOLD) return;

      const stamp = Date.now();
      const extractLike = /extract|xlsx|csv|table|ingest/i.test(tool);
      const root = extractLike ? "outputs/extracted" : "outputs/mcp";
      const relative = `${root}/${safeName(tool)}/${stamp}.json`;
      const dest = `${directory}/${relative}`;
      const destFile = Bun.file(dest);
      await Bun.write(
        destFile,
        JSON.stringify(
          {
            tool,
            written_at: new Date(stamp).toISOString(),
            char_count: body.length,
            body,
          },
          null,
          2
        )
      );

      const digest = digestText(body, tool);
      output.output = digest;
      const content = (output as { content?: unknown }).content;
      if (Array.isArray(content)) {
        (output as { content: unknown[] }).content = [
          { type: "text", text: digest },
        ];
      }
    },
  };
}) satisfies Plugin;
