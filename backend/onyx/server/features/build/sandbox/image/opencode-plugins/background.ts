# Background-process tool for the sandbox's opencode agent.

Talks to the in-pod sandbox daemon (localhost) — the data plane never
crosses to the host. The `background` tool: start (returns process_id
immediately), poll (byte-cursor output + status), send_input, stop, list.
Matches the plan-4 wake semantics: watch the process from the host side by
asking for a `watch` action; the session wakes when the pattern hits.

import type { Plugin } from "@opencode-ai/plugin";
import { tool } from "@opencode-ai/plugin";

const DAEMON_PORT = 8731;

interface ProcessStartResult {
  process_id: string;
  pid: number;
}

interface ProcessPollResult {
  chunk: string;
  new_cursor: number;
  status: string;
  exit_code: number | null;
}

async function daemonCall(
  path: string,
  method: "GET" | "POST",
  body?: unknown
): Promise<unknown> {
  const res = await fetch(`http://127.0.0.1:${DAEMON_PORT}${path}`, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const text = await res.text();
  if (!res.ok) {
    throw new Error(`background ${path} failed: ${res.status} ${text.slice(0, 200)}`);
  }
  return text ? JSON.parse(text) : null;
}

export default (async () => {
  return {
    tool: {
      background: tool({
        description:
          "Run a long-lived shell command in this sandbox without blocking " +
          "the conversation. Returns a process_id immediately; poll its " +
          "output with the poll action; feed stdin with send_input; stop " +
          "with stop. Processes keep running between messages and die with " +
          "the sandbox.",
        args: {
          action: tool.schema.enum([
            "start",
            "poll",
            "send_input",
            "stop",
            "list",
          ]).describe("What to do"),
          command: tool.schema
            .string()
            .optional()
            .describe("Shell command (required for start)"),
          process_id: tool.schema
            .string()
            .optional()
            .describe("Process id (required for poll/send_input/stop)"),
          data: tool.schema
            .string()
            .optional()
            .describe("Data to write to stdin (send_input)"),
          cursor: tool.schema
            .number()
            .optional()
            .describe("Byte cursor from the previous poll (poll)"),
        },
        async execute(args) {
          try {
            if (args.action === "start") {
              if (!args.command) {
                return "Error: start requires `command`.";
              }
              const r = (await daemonCall("/processes", "POST", {
                command: args.command,
                kind: "background",
              })) as ProcessStartResult;
              return (
                `Started in the background.\nprocess_id: ${r.process_id}\n` +
                "Poll it with background(action='poll', " +
                `process_id='${r.process_id}', cursor=<last cursor>).`
              );
            }
            if (args.action === "poll") {
              if (!args.process_id) {
                return "Error: poll requires `process_id`.";
              }
              const r = (await daemonCall(
                `/processes/${args.process_id}/poll`,
                "POST",
                { cursor: args.cursor ?? 0 }
              )) as ProcessPollResult;
              return (
                `status: ${r.status}` +
                (r.exit_code !== null ? ` (exit ${r.exit_code})` : "") +
                `\ncursor: ${r.new_cursor}\n\n${r.chunk || "(no new output)"}`
              );
            }
            if (args.action === "send_input") {
              if (!args.process_id) {
                return "Error: send_input requires `process_id`.";
              }
              await daemonCall(
                `/processes/${args.process_id}/input`,
                "POST",
                { data: args.data ?? "" }
              );
              return "Input written.";
            }
            if (args.action === "stop") {
              if (!args.process_id) {
                return "Error: stop requires `process_id`.";
              }
              await daemonCall(`/processes/${args.process_id}/stop`, "POST", {
                signal: "TERM",
              });
              return "Stop signal sent.";
            }
            if (args.action === "list") {
              const rows = (await daemonCall(
                "/processes-list",
                "GET"
              )) as Array<{
                process_id: string;
                status: string;
                command: string;
              }>;
              if (!rows.length) {
                return "No background processes.";
              }
              return rows
                .map(
                  (r) =>
                    `${r.process_id} [${r.status}] ${r.command.slice(0, 120)}`
                )
                .join("\n");
            }
            return "Error: unknown action.";
          } catch (e) {
            return `background error: ${e instanceof Error ? e.message : e}`;
          }
        },
      }),
    },
  };
}) as Plugin;
