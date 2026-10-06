import type { TapeEventItem } from "@/lib/craft-tape/types";

/**
 * One-line human summaries for taped harness events. Tapes store raw harness
 * payloads verbatim (opencode `message.part.*`, codex `item/*`, context
 * markers), and the trajectory ledger shows one line per event — this pulls
 * the most meaningful fragment out instead of dumping JSON.
 */

function asRecord(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null
    ? (value as Record<string, unknown>)
    : null;
}

function asString(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

const SUMMARY_MAX_CHARS = 140;

function compact(text: string): string {
  const flat = text.replace(/\s+/g, " ").trim();
  return flat.length > SUMMARY_MAX_CHARS
    ? `${flat.slice(0, SUMMARY_MAX_CHARS)}…`
    : flat;
}

/**
 * Summarize one event for the ledger. Returns null when there is nothing
 * worth saying beyond the subtype badge (e.g. delta chunks, which the ledger
 * collapses into run rows anyway).
 */
export function summarizeEvent(event: TapeEventItem): string | null {
  if (event.kind === "context_event") {
    const reason = asString(event.payload.reason);
    return reason ? compact(reason) : null;
  }

  const props = asRecord(event.payload.properties);
  if (props) {
    const part = asRecord(props.part);
    if (part) return compact(summarizePart(part));
    if (typeof props.delta === "string") return null;
    const status = asRecord(props.status);
    if (status) {
      const state = asString(status.type);
      return state ? compact(state) : null;
    }
    const info = asRecord(props.info);
    if (info) {
      const role = asString(info.role);
      return role ? compact(`${role} message`) : null;
    }
    if (props.error !== undefined) {
      const message =
        asString(props.error) ?? JSON.stringify(props.error) ?? null;
      return message ? compact(message) : null;
    }
  }

  const item = asRecord(event.payload.item);
  if (item) {
    const text =
      asString(item.text) ??
      asString(item.command) ??
      asString((asRecord(item.input) ?? {})["command"]);
    if (text) return compact(text);
  }

  for (const key of ["message", "text", "command", "reason", "summary"]) {
    const value = asString(event.payload[key]);
    if (value) return compact(value);
  }
  return null;
}

function summarizePart(part: Record<string, unknown>): string {
  switch (asString(part.type)) {
    case "tool": {
      const state = asRecord(part.state);
      const input = asRecord(state?.input);
      const command =
        asString(input?.command) ??
        asString(input?.filePath) ??
        asString(input?.url) ??
        compact(JSON.stringify(input ?? {}));
      return `${asString(part.tool) ?? "tool"}: ${command}`;
    }
    case "step-finish": {
      const tokens = asRecord(part.tokens);
      const output = typeof tokens?.output === "number" ? tokens.output : null;
      const reason = asString(part.reason);
      return [
        "step finish",
        reason ? `(${reason})` : null,
        output !== null ? `· ${output} out tok` : null,
      ]
        .filter(Boolean)
        .join(" ");
    }
    default:
      return asString(part.text) ?? "";
  }
}

/**
 * The ledger collapses consecutive delta chunks (opencode
 * `message.part.delta`, codex `item/*delta`) into one run row — they carry
 * no per-event meaning and would flood the timeline otherwise.
 */
export function isDeltaEvent(event: TapeEventItem): boolean {
  if (event.subtype === "message.part.delta") return true;
  return event.subtype.startsWith("codex:") && event.subtype.endsWith("/delta");
}
