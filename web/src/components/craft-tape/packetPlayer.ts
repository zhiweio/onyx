"use client";

/**
 * Packet reducer for tape replay: applies one live-format packet to a
 * StreamItem list — the same classification (`parsePacket`) and item
 * semantics the craft live stream uses, distilled to a pure function so
 * the replay player can fold any event prefix without the craft store
 * (dsh discipline: live and replay share one interpretation path).
 */

import type { StreamItem, ToolCallState } from "@/app/craft/types/displayTypes";
import { parsePacket } from "@/app/craft/utils/parsePacket";
import type { ReplayPacketItem } from "@/lib/craft-tape/types";

/** codex live events use ACP-2.0 sessionUpdate names; the shared parsers
 * classify the 1.x names. Alias them here (replay view only). */
function normalizeSessionUpdate(
  packet: Record<string, unknown>
): Record<string, unknown> {
  const update = packet.sessionUpdate ?? packet.type;
  if (update === "tool_call")
    return { ...packet, sessionUpdate: "tool_call_start" };
  if (update === "tool_call_update")
    return { ...packet, sessionUpdate: "tool_call_progress" };
  return packet;
}

let idCounter = 0;
function nextId(prefix: string): string {
  idCounter += 1;
  return `replay-${prefix}-${idCounter}`;
}

function settleTrailing(items: StreamItem[]): StreamItem[] {
  const last = items[items.length - 1];
  if (last && (last.type === "text" || last.type === "thinking")) {
    return [...items.slice(0, -1), { ...last, isStreaming: false }];
  }
  return items;
}

/** Apply one replay packet; returns the updated item list. */
export function applyReplayPacket(
  items: StreamItem[],
  entry: ReplayPacketItem
): StreamItem[] {
  if (entry.type !== "packet" || !entry.packet) {
    return items;
  }
  const packet = parsePacket(normalizeSessionUpdate(entry.packet));

  switch (packet.type) {
    case "text_chunk": {
      if (!packet.text) return items;
      const last = items[items.length - 1];
      if (last && last.type === "text" && last.isStreaming) {
        return [
          ...items.slice(0, -1),
          { ...last, content: last.content + packet.text },
        ];
      }
      return [
        ...settleTrailing(items),
        {
          type: "text",
          id: nextId("text"),
          content: packet.text,
          isStreaming: true,
        },
      ];
    }
    case "thinking_chunk": {
      if (!packet.text) return items;
      const last = items[items.length - 1];
      if (last && last.type === "thinking" && last.isStreaming) {
        return [
          ...items.slice(0, -1),
          { ...last, content: last.content + packet.text },
        ];
      }
      return [
        ...settleTrailing(items),
        {
          type: "thinking",
          id: nextId("think"),
          content: packet.text,
          isStreaming: true,
        },
      ];
    }
    case "tool_call_start": {
      const toolCall: ToolCallState = {
        id: packet.toolCallId,
        kind: packet.kind,
        toolName: packet.toolName,
        title: packet.title,
        description: packet.description,
        command: packet.command,
        status: "in_progress",
        rawOutput: "",
      };
      return [
        ...settleTrailing(items),
        { type: "tool_call", id: packet.toolCallId, toolCall },
      ];
    }
    case "tool_call_progress": {
      if (packet.isTodo) {
        const idx = items.findIndex(
          (item) =>
            item.type === "todo_list" && item.todoList.id === packet.toolCallId
        );
        if (idx >= 0) {
          const existing = items[idx];
          if (existing && existing.type === "todo_list") {
            const next = [...items];
            next[idx] = {
              ...existing,
              todoList: { ...existing.todoList, todos: packet.todos },
            };
            return next;
          }
        }
        return [
          ...items,
          {
            type: "todo_list",
            id: packet.toolCallId,
            todoList: {
              id: packet.toolCallId,
              todos: packet.todos,
              isOpen: false,
            },
          },
        ];
      }
      const idx = items.findIndex(
        (item) =>
          item.type === "tool_call" && item.toolCall.id === packet.toolCallId
      );
      if (idx < 0) {
        const toolCall: ToolCallState = {
          id: packet.toolCallId,
          kind: packet.kind,
          toolName: packet.toolName,
          title: packet.title,
          description: packet.description,
          command: packet.command,
          status: packet.status,
          rawOutput: packet.rawOutput,
        };
        return [
          ...items,
          { type: "tool_call", id: packet.toolCallId, toolCall },
        ];
      }
      const existing = items[idx];
      if (existing && existing.type === "tool_call") {
        const next = [...items];
        next[idx] = {
          ...existing,
          toolCall: {
            ...existing.toolCall,
            status: packet.status,
            rawOutput: packet.rawOutput || existing.toolCall.rawOutput,
            title: packet.title || existing.toolCall.title,
            description: packet.description || existing.toolCall.description,
          },
        };
        return next;
      }
      return items;
    }
    case "compaction":
      return [
        ...settleTrailing(items),
        {
          type: "compaction",
          id: nextId("compaction"),
          summary: packet.summary ?? null,
        },
      ];
    case "error":
      return [
        ...settleTrailing(items),
        { type: "error", id: nextId("error"), content: packet.message ?? "" },
      ];
    case "prompt_response":
      return settleTrailing(items);
    default:
      return items;
  }
}
