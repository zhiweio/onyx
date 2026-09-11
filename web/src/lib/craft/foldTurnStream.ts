import type { RateLimitDetails } from "@/app/app/interfaces";
import type {
  StreamItem,
  TodoListState,
  ToolCallState,
} from "@/app/craft/types/displayTypes";

export type ToolPhase = "explore" | "edit" | "run" | "task" | "other";

export type FoldRow =
  | {
      kind: "thought";
      id: string;
      content: string;
      isStreaming: boolean;
      durationMs?: number;
      summary?: string;
    }
  | {
      kind: "tools";
      id: string;
      phase: ToolPhase;
      tools: ToolCallState[];
      summary?: string;
    }
  | { kind: "text"; id: string; content: string; isStreaming: boolean }
  | { kind: "todo_list"; id: string; todoList: TodoListState }
  | {
      kind: "connect_app_request";
      id: string;
      requestId: string;
      externalAppId: number;
      reason: string | null;
    }
  | { kind: "compaction"; id: string; summary: string | null }
  | {
      kind: "error";
      id: string;
      content: string;
      rateLimit?: RateLimitDetails;
    };

export interface FoldedTurn {
  rows: FoldRow[];
  answer: { id: string; content: string; isStreaming: boolean } | null;
  showPlanningNext: boolean;
}

export function classifyToolPhase(tool: ToolCallState): ToolPhase {
  if (tool.toolName === "task" || tool.kind === "task") {
    const sub = (tool.subagentType || "").toLowerCase();
    if (sub === "explore") return "explore";
    return "task";
  }
  if (
    tool.kind === "read" ||
    tool.kind === "search" ||
    tool.toolName === "list" ||
    tool.toolName === "webfetch" ||
    tool.toolName === "websearch" ||
    tool.toolName === "skill"
  ) {
    return "explore";
  }
  if (tool.kind === "edit") return "edit";
  if (tool.kind === "execute") return "run";
  return "other";
}

function isSettledTool(tool: ToolCallState): boolean {
  return (
    tool.status === "completed" ||
    tool.status === "failed" ||
    tool.status === "cancelled"
  );
}

function isLiveWork(items: StreamItem[]): boolean {
  return items.some((item) => {
    if (item.type === "thinking" && item.isStreaming) return true;
    if (item.type === "text" && item.isStreaming) return true;
    if (
      item.type === "tool_call" &&
      (item.toolCall.status === "pending" ||
        item.toolCall.status === "in_progress")
    ) {
      return true;
    }
    return false;
  });
}

function trailingTextStart(items: StreamItem[]): number {
  let start = items.length;
  for (let i = items.length - 1; i >= 0; i--) {
    if (items[i]!.type === "text") {
      start = i;
      continue;
    }
    break;
  }
  return start;
}

export function foldTurnStream(
  items: StreamItem[],
  opts: { isStreaming: boolean }
): FoldedTurn {
  const answerStart = trailingTextStart(items);
  const trailing = items
    .slice(answerStart)
    .filter((item): item is Extract<StreamItem, { type: "text" }> => {
      return item.type === "text";
    });
  const answer =
    trailing.length > 0
      ? {
          id: trailing[trailing.length - 1]!.id,
          content: trailing.map((item) => item.content).join(""),
          isStreaming: trailing.some((item) => item.isStreaming),
        }
      : null;
  const body = answer !== null ? items.slice(0, answerStart) : items;

  let nextGroup = 0;
  let currentPhase: ToolPhase | null = null;
  let currentGroup = -1;
  const groupTools = new Map<number, ToolCallState[]>();
  const toolGroup = new Map<string, number>();

  for (const item of body) {
    if (item.type === "tool_call") {
      const phase = classifyToolPhase(item.toolCall);
      if (phase !== currentPhase) {
        nextGroup += 1;
        currentGroup = nextGroup;
        currentPhase = phase;
      }
      const tools = groupTools.get(currentGroup) ?? [];
      tools.push(item.toolCall);
      groupTools.set(currentGroup, tools);
      toolGroup.set(item.id, currentGroup);
      continue;
    }
    if (item.type === "thinking") {
      continue;
    }
    currentPhase = null;
  }

  const emitted = new Set<number>();
  const rows: FoldRow[] = [];
  for (const item of body) {
    if (item.type === "thinking") {
      if (!item.content) continue;
      const last = rows[rows.length - 1];
      if (last?.kind === "thought") {
        last.content = `${last.content}\n\n${item.content}`;
        last.isStreaming = item.isStreaming;
        if (item.durationMs != null || last.durationMs != null) {
          last.durationMs = (last.durationMs ?? 0) + (item.durationMs ?? 0);
        }
        continue;
      }
      rows.push({
        kind: "thought",
        id: item.id,
        content: item.content,
        isStreaming: item.isStreaming,
        durationMs: item.durationMs,
      });
      continue;
    }
    if (item.type === "tool_call") {
      const groupId = toolGroup.get(item.id);
      if (groupId == null || emitted.has(groupId)) continue;
      emitted.add(groupId);
      const tools = groupTools.get(groupId) ?? [item.toolCall];
      rows.push({
        kind: "tools",
        id: `tools-${tools[0]!.id}`,
        phase: classifyToolPhase(tools[0]!),
        tools,
      });
      continue;
    }
    if (item.type === "text") {
      rows.push({
        kind: "text",
        id: item.id,
        content: item.content,
        isStreaming: item.isStreaming,
      });
      continue;
    }
    if (item.type === "todo_list") {
      rows.push({
        kind: "todo_list",
        id: item.id,
        todoList: item.todoList,
      });
      continue;
    }
    if (item.type === "connect_app_request") {
      rows.push({
        kind: "connect_app_request",
        id: item.id,
        requestId: item.requestId,
        externalAppId: item.externalAppId,
        reason: item.reason,
      });
      continue;
    }
    if (item.type === "compaction") {
      rows.push({
        kind: "compaction",
        id: item.id,
        summary: item.summary,
      });
      continue;
    }
    if (item.type === "error") {
      rows.push({
        kind: "error",
        id: item.id,
        content: item.content,
        rateLimit: item.rateLimit,
      });
    }
  }

  applyStepSummaries(rows);

  const lastBody = body[body.length - 1];
  let showPlanningNext = false;
  if (opts.isStreaming && answer === null && lastBody && !isLiveWork(items)) {
    if (lastBody.type === "thinking" && !lastBody.isStreaming) {
      showPlanningNext = true;
    }
    if (lastBody.type === "tool_call" && isSettledTool(lastBody.toolCall)) {
      showPlanningNext = true;
    }
  }

  return { rows, answer, showPlanningNext };
}

export function toolBatchIsLive(tools: ToolCallState[]): boolean {
  return tools.some(
    (tool) => tool.status === "pending" || tool.status === "in_progress"
  );
}

export function toolTarget(tool: ToolCallState): string {
  return tool.description || tool.command || tool.title;
}

const STEP_FILLER =
  /^(good|ok|okay|done|yes|yeah|yep|interesting|thanks|got it|cool|nice|right|sure|the output is offloaded|offloaded again)[.!]?$/i;

function stripStepMarkup(text: string): string {
  return text
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/[#*_`>]+/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function splitStepSentences(plain: string): string[] {
  return plain
    .split(/(?<=[。！？])|(?<=[.!?])(?:\s+|$)/)
    .map((part) => part.trim())
    .filter(Boolean);
}

function isUsefulStepSentence(sentence: string): boolean {
  const trimmed = sentence.replace(/["“”'‘’]/g, "").trim();
  if (!trimmed || STEP_FILLER.test(trimmed)) return false;
  const han = [...trimmed].filter((ch) => /\p{Script=Han}/u.test(ch)).length;
  if (han > 0) return han >= 6;
  return trimmed.replace(/[^A-Za-z]/g, "").length >= 12;
}

function clampStepSentence(sentence: string, max: number): string {
  if (sentence.length <= max) return sentence;
  return `${sentence.slice(0, Math.max(1, max - 1)).trimEnd()}…`;
}

/** First useful sentence for a Cursor-style step line. Strips light markdown. */
export function stepSummary(text: string, max = 160): string {
  const plain = stripStepMarkup(text);
  if (!plain) return "";
  const sentences = splitStepSentences(plain);
  const useful = sentences.find(isUsefulStepSentence);
  const fallback = sentences.find((sentence) => {
    const trimmed = sentence.replace(/["“”'‘’]/g, "").trim();
    return trimmed.length >= 8 && !STEP_FILLER.test(trimmed);
  });
  const picked = useful ?? fallback ?? "";
  if (!picked) return "";
  return clampStepSentence(picked, max);
}

/** Short label for a path or command in a phase header. */
export function shortPhaseTarget(target: string, max = 48): string {
  const trimmed = target.trim().replace(/\s+/g, " ");
  if (!trimmed) return "";
  if (trimmed.length <= max) return trimmed;
  const slash = trimmed.lastIndexOf("/");
  if (slash >= 0) {
    const base = trimmed.slice(slash + 1);
    if (base.length >= 4 && base.length <= max) return base;
  }
  return `${trimmed.slice(0, Math.max(1, max - 1)).trimEnd()}…`;
}

function applyStepSummaries(rows: FoldRow[]): void {
  for (let i = rows.length - 1; i >= 0; i -= 1) {
    const row = rows[i];
    if (row?.kind !== "text") continue;
    const prev = rows[i - 1];
    if (prev?.kind !== "thought" && prev?.kind !== "tools") continue;
    const summary = stepSummary(row.content);
    if (!summary) continue;
    prev.summary = summary;
    rows.splice(i, 1);
  }

  for (let i = 0; i < rows.length; i += 1) {
    const row = rows[i];
    if (row?.kind !== "tools" || row.summary) continue;
    const next = rows[i + 1];
    if (next?.kind !== "thought") continue;
    const summary = stepSummary(next.content);
    if (!summary) continue;
    row.summary = summary;
  }

  for (const row of rows) {
    if (row.kind !== "thought" || row.summary) continue;
    row.summary = stepSummary(row.content) || undefined;
  }

  for (let i = 1; i < rows.length; i += 1) {
    const row = rows[i];
    const prev = rows[i - 1];
    if (row?.kind !== "thought" || !row.summary) continue;
    if (
      (prev?.kind === "thought" || prev?.kind === "tools") &&
      prev.summary === row.summary
    ) {
      row.summary = undefined;
    }
  }
}
