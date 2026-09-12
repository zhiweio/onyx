"use client";

import TaskBody from "@/app/craft/components/tool-cards/TaskBody";
import ToolActivityLine from "@/app/craft/components/turn-activity/ToolActivityLine";
import type { ToolCallState } from "@/app/craft/types/displayTypes";

export default function ActivityToolLine({
  toolCall,
}: {
  toolCall: ToolCallState;
}) {
  if (toolCall.kind === "task") {
    return <TaskBody toolCall={toolCall} />;
  }
  return <ToolActivityLine toolCall={toolCall} />;
}
