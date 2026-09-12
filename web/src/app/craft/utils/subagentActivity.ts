import type {
  StreamItem,
  SubagentState,
  ToolCallState,
} from "@/app/craft/types/displayTypes";

const BUILD_SESSION_ID =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function isBuildSessionId(value: string): boolean {
  return BUILD_SESSION_ID.test(value);
}

export function activityFromToolCall(toolCall: ToolCallState): string {
  return (
    toolCall.description ||
    toolCall.title ||
    toolCall.command ||
    ""
  ).trim();
}

export function activityFromStreamItems(items: StreamItem[]): string {
  for (let index = items.length - 1; index >= 0; index -= 1) {
    const item = items[index];
    if (!item) continue;
    if (item.type === "tool_call") {
      const label = activityFromToolCall(item.toolCall);
      if (label) return label;
    }
    if (item.type === "thinking" || item.type === "text") {
      const line = item.content.trim().split("\n")[0]?.trim() ?? "";
      if (line) return line;
    }
  }
  return "";
}

export function latestSubagentActivity(subagent: SubagentState | null): string {
  if (!subagent) return "";
  const lastTurn = subagent.turns[subagent.turns.length - 1];
  const fromItems = lastTurn
    ? activityFromStreamItems(lastTurn.streamItems)
    : "";
  return fromItems || subagent.lastActivity || "";
}

export function specialistUiStatus(status: string): {
  tool: ToolCallState["status"];
  subagent: SubagentState["status"];
} {
  if (status === "succeeded") {
    return { tool: "completed", subagent: "done" };
  }
  if (status === "failed") {
    return { tool: "failed", subagent: "failed" };
  }
  return { tool: "in_progress", subagent: "running" };
}
