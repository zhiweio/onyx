"use client";

import { useEffect } from "react";
import {
  fetchActiveTurn,
  fetchMessages,
  fetchTurnEventStream,
  processSSEStream,
} from "@/app/craft/services/apiServices";
import { useBuildSessionStore } from "@/app/craft/hooks/useBuildSessionStore";
import { parsePacket } from "@/app/craft/utils/parsePacket";
import {
  toolCallStateFromProgress,
  toolCallStateFromStart,
} from "@/app/craft/utils/subagentRouting";
import { isBuildSessionId } from "@/app/craft/utils/subagentActivity";

function applyChildPacket(
  parentSessionId: string,
  childSessionId: string,
  parentToolCallId: string,
  raw: unknown
): void {
  const parsed = parsePacket(raw);
  const store = useBuildSessionStore.getState();
  switch (parsed.type) {
    case "text_chunk":
      if (parsed.text) {
        store.appendSubagentResponseChunk(
          parentSessionId,
          childSessionId,
          parsed.text
        );
      }
      break;
    case "thinking_chunk":
      if (parsed.text) {
        store.appendSubagentThinkingChunk(
          parentSessionId,
          childSessionId,
          parsed.text
        );
      }
      break;
    case "tool_call_start":
      store.recordSubagentToolCall(
        parentSessionId,
        childSessionId,
        parentToolCallId,
        toolCallStateFromStart(parsed),
        parsed.subagentType,
        ""
      );
      break;
    case "tool_call_progress":
      store.recordSubagentToolCall(
        parentSessionId,
        childSessionId,
        parentToolCallId,
        toolCallStateFromProgress(parsed),
        parsed.subagentType,
        ""
      );
      break;
    default:
      break;
  }
}

export function useLaneTranscript({
  open,
  parentSessionId,
  childSessionId,
  parentToolCallId,
  running,
}: {
  open: boolean;
  parentSessionId: string | null;
  childSessionId: string | null;
  parentToolCallId: string;
  running: boolean;
}): void {
  useEffect(() => {
    if (!open || !parentSessionId || !childSessionId) return;
    if (!isBuildSessionId(childSessionId)) return;

    const abort = new AbortController();

    void (async () => {
      try {
        const messages = await fetchMessages(childSessionId);
        if (abort.signal.aborted) return;
        useBuildSessionStore
          .getState()
          .hydrateSubagentFromMessages(
            parentSessionId,
            childSessionId,
            messages
          );
        if (!running) return;
        const turn = await fetchActiveTurn(childSessionId);
        if (abort.signal.aborted || !turn?.turn_id) return;
        const response = await fetchTurnEventStream(
          childSessionId,
          turn.turn_id,
          abort.signal
        );
        if (!response) return;
        await processSSEStream(response, (packet) => {
          if (abort.signal.aborted) return;
          applyChildPacket(
            parentSessionId,
            childSessionId,
            parentToolCallId,
            packet
          );
        });
      } catch {
        // The row still shows last_activity from the job poll.
      }
    })();

    return () => abort.abort();
  }, [open, parentSessionId, childSessionId, parentToolCallId, running]);
}
