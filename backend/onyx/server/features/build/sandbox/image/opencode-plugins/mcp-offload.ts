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

function digestText(path: string, body: string, tool: string): string {
  const preview = body.slice(0, PREVIEW_CHARS);
  return (
    `[Onyx MCP offload] ${tool} returned ${body.length} chars. ` +
    `Full result is on disk at ${path}. Use that file; do not ask for the ` +
    `full body again.\n\nPreview:\n${preview}`
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
      if (body.length < OFFLOAD_THRESHOLD) return;

      const stamp = Date.now();
      const relative = `outputs/mcp/${safeName(tool)}/${stamp}.json`;
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

      const digest = digestText(relative, body, tool);
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
