import type {
  StreamItem,
  SubagentState,
  ToolCallState,
} from "@/app/craft/types/displayTypes";

const LANE_TASK_PREFIX = "lane-task-";
const LANE_TASK_STATUS_SUFFIX =
  /-(in_progress|completed|failed|cancelled|pending)$/;

export function laneTaskToolId(nodeId: string): string {
  return `${LANE_TASK_PREFIX}${nodeId}`;
}

/** Node id from a stable or status-suffixed lane-task tool id. */
export function laneTaskNodeIdFromToolId(toolId: string): string | null {
  if (!toolId.startsWith(LANE_TASK_PREFIX)) return null;
  const rest = toolId.slice(LANE_TASK_PREFIX.length);
  if (!rest) return null;
  return rest.replace(LANE_TASK_STATUS_SUFFIX, "");
}

/**
 * Match a parent task card to a specialist. Old cards used
 * `lane-task-{node}-{status}`; new cards use `lane-task-{node}`.
 * Do not use a raw prefix — `lane:researcher` must not match
 * `lane:researcher-2`.
 */
export function matchesLaneTaskToolId(
  itemId: string,
  otherId: string
): boolean {
  const left = laneTaskNodeIdFromToolId(itemId);
  const right = laneTaskNodeIdFromToolId(otherId);
  if (left && right) return left === right;
  return itemId === otherId;
}

const SETTLED_TOOL_STATUSES: ReadonlySet<ToolCallState["status"]> = new Set([
  "completed",
  "failed",
  "cancelled",
]);

const LIVE_JOB_STATUSES: ReadonlySet<string> = new Set([
  "pending",
  "running",
  "waiting_specialists",
  "waiting_lanes",
  "interrupted",
]);

export function isSettledToolStatus(status: ToolCallState["status"]): boolean {
  return SETTLED_TOOL_STATUSES.has(status);
}

export function jobStatusIsLive(jobStatus?: string | null): boolean {
  return !!jobStatus && LIVE_JOB_STATUSES.has(jobStatus);
}

export function lastUserMessageIndex(
  messages: ReadonlyArray<{ type?: string }>
): number {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    if (messages[index]?.type === "user") return index;
  }
  return -1;
}

export function laneTaskCardIsEligible(
  item: StreamItem,
  parentToolCallId: string,
  specialistSessionId: string,
  allowUnbound: boolean
): boolean {
  if (item.type !== "tool_call") return false;
  if (!matchesLaneTaskToolId(item.toolCall.id, parentToolCallId)) return false;
  if (isSettledToolStatus(item.toolCall.status)) return false;
  const bound = item.toolCall.subagentSessionId;
  if (bound && bound !== specialistSessionId) return false;
  if (!bound && !allowUnbound) return false;
  return true;
}

export function patchLaneTaskToolCalls(
  items: StreamItem[],
  toolCallId: string,
  updates: Partial<ToolCallState>,
  allowUnbound: boolean
): StreamItem[] {
  const specialistSessionId = updates.subagentSessionId ?? "";
  let target = -1;
  items.forEach((item, index) => {
    if (
      laneTaskCardIsEligible(
        item,
        toolCallId,
        specialistSessionId,
        allowUnbound
      )
    ) {
      target = index;
    }
  });
  if (target < 0) return items;
  return items.map((item, index) => {
    if (index !== target || item.type !== "tool_call") return item;
    return {
      ...item,
      toolCall: { ...item.toolCall, ...updates },
    };
  });
}

export function pinForeignLaneTaskCards(
  items: StreamItem[],
  liveSessionIds: ReadonlySet<string>
): StreamItem[] {
  if (liveSessionIds.size === 0) return items;
  return items.map((item) => {
    if (item.type !== "tool_call") return item;
    if (!laneTaskNodeIdFromToolId(item.toolCall.id)) return item;
    if (isSettledToolStatus(item.toolCall.status)) return item;
    const bound = item.toolCall.subagentSessionId;
    if (!bound || liveSessionIds.has(bound)) return item;
    return { ...item, toolCall: { ...item.toolCall, status: "cancelled" } };
  });
}

export function makeLaneTaskStreamItem(args: {
  nodeId: string;
  role: string;
  name: string;
  status: ToolCallState["status"];
  sessionId: string;
  jobId?: string;
}): StreamItem {
  const id = laneTaskToolId(args.nodeId);
  return {
    type: "tool_call",
    id,
    toolCall: {
      id,
      kind: "task",
      toolName: "task",
      title: args.name,
      description: args.name,
      command: "",
      status: args.status,
      rawOutput: "",
      subagentType: args.role,
      subagentSessionId: args.sessionId,
      jobId: args.jobId,
    },
  };
}

export function dropLaneTaskCards(items: StreamItem[]): StreamItem[] {
  return items.filter((item) => {
    if (item.type !== "tool_call") return true;
    return laneTaskNodeIdFromToolId(item.toolCall.id) == null;
  });
}

export function settleOpenLaneTaskCards(
  items: StreamItem[],
  status: Extract<ToolCallState["status"], "failed" | "cancelled">
): StreamItem[] {
  return items.map((item) => {
    if (item.type !== "tool_call") return item;
    if (!laneTaskNodeIdFromToolId(item.toolCall.id)) return item;
    if (SETTLED_TOOL_STATUSES.has(item.toolCall.status)) return item;
    return {
      ...item,
      toolCall: { ...item.toolCall, status },
    };
  });
}

type TranscriptMessage = {
  message_metadata?: { streamItems?: StreamItem[] } | null;
};

/** Derive cancelled/failed lane cards for display. Do not wait on store sync. */
export function settleTranscriptForJobStatus<T extends TranscriptMessage>(
  messages: T[],
  streamItems: StreamItem[],
  jobStatus?: string | null
): { messages: T[]; streamItems: StreamItem[] } {
  if (jobStatus !== "cancelled" && jobStatus !== "failed") {
    return { messages, streamItems };
  }
  const settleStatus = jobStatus === "cancelled" ? "cancelled" : "failed";
  return {
    streamItems: settleOpenLaneTaskCards(streamItems, settleStatus),
    messages: messages.map((message) => {
      const items = message.message_metadata?.streamItems;
      if (!Array.isArray(items)) return message;
      return {
        ...message,
        message_metadata: {
          ...message.message_metadata,
          streamItems: settleOpenLaneTaskCards(items, settleStatus),
        },
      };
    }),
  };
}

export function taskRowStatus(
  subagentStatus: SubagentState["status"] | undefined,
  toolStatus: ToolCallState["status"],
  specialistStatus?: string,
  jobStatus?: string
): SubagentState["status"] {
  if (
    specialistStatus === "succeeded" ||
    subagentStatus === "done" ||
    toolStatus === "completed"
  ) {
    return "done";
  }
  if (
    jobStatus === "cancelled" ||
    jobStatus === "failed" ||
    specialistStatus === "failed" ||
    toolStatus === "failed" ||
    toolStatus === "cancelled"
  ) {
    return "failed";
  }
  return subagentStatus ?? "running";
}

export function childSessionIdForTask(
  toolCallId: string,
  toolCallSessionId: string | undefined,
  subagents: Iterable<{ sessionId: string; parentToolCallId: string }>,
  options?: { allowRematch?: boolean }
): string | null {
  if (toolCallSessionId) return toolCallSessionId;
  if (options?.allowRematch === false) return null;
  for (const entry of subagents) {
    if (
      entry.parentToolCallId &&
      matchesLaneTaskToolId(toolCallId, entry.parentToolCallId)
    ) {
      return entry.sessionId;
    }
  }
  return null;
}

const LANE_FILE_IN_PATH = /(?:outputs|markdown|normalized)\/[^\s`"'<>]+/i;
const LANE_TRAILING_FILE = /([^\s/`"'<>]+\.(md|csv|json|txt|tsv|yml|yaml))$/i;

/** File name from a lane card label such as `Researcher — outputs/a.md`. */
export function filenameFromLaneLabel(text: string): string {
  const trimmed = text.trim();
  if (!trimmed) return "";
  const pathMatch = trimmed.match(LANE_FILE_IN_PATH);
  if (pathMatch) {
    const parts = pathMatch[0].split("/");
    return parts[parts.length - 1] ?? "";
  }
  const afterDash = trimmed.split(/\s+[—–]\s+/);
  if (afterDash.length > 1) {
    const tail = afterDash[afterDash.length - 1]?.trim() ?? "";
    const file = tail.split("/").pop() ?? "";
    if (file && LANE_TRAILING_FILE.test(file)) return file;
  }
  const trailing = trimmed.match(LANE_TRAILING_FILE);
  return trailing?.[1] ?? "";
}

export function isGenericRoleLabel(
  name: string,
  role: string | null | undefined
): boolean {
  const normalizedName = name.trim().toLowerCase();
  if (!normalizedName) return true;
  const normalizedRole = (role ?? "").trim().toLowerCase();
  return !!normalizedRole && normalizedName === normalizedRole;
}

type LaneTaskCardItem = {
  type?: string;
  id?: string;
  toolCall?: {
    id: string;
    title?: string;
    description?: string;
    status?: ToolCallState["status"];
  };
};

/** Description (or title) of the parent task card for a lane tool id. */
export function laneTaskCardLabel(
  items: ReadonlyArray<LaneTaskCardItem>,
  parentToolCallId: string
): string {
  let fallback = "";
  for (let index = items.length - 1; index >= 0; index -= 1) {
    const item = items[index];
    if (!item || item.type !== "tool_call" || !item.toolCall) continue;
    const itemId = item.toolCall.id || item.id || "";
    if (!matchesLaneTaskToolId(itemId, parentToolCallId)) continue;
    const label = item.toolCall.description || item.toolCall.title || "";
    if (!label) continue;
    const status = item.toolCall.status;
    if (!status || !isSettledToolStatus(status)) return label;
    if (!fallback) fallback = label;
  }
  return fallback;
}

/** Short switcher title so seven Researcher lanes stay distinct. */
export function subagentSwitcherLabel(
  name: string,
  role: string | null | undefined,
  lastActivity?: string | null
): string {
  const fromName = filenameFromLaneLabel(name);
  if (fromName) return fromName;
  const fromActivity = filenameFromLaneLabel(lastActivity ?? "");
  if (fromActivity) return fromActivity;
  if (name && !isGenericRoleLabel(name, role)) return name;
  return name || role || "";
}
