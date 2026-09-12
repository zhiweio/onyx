import {
  activityFromStreamItems,
  isBuildSessionId,
  latestSubagentActivity,
  specialistUiStatus,
} from "@/app/craft/utils/subagentActivity";
import type { SubagentState } from "@/app/craft/types/displayTypes";

describe("subagentActivity", () => {
  it("accepts build session ids and rejects OpenCode ids", () => {
    expect(isBuildSessionId("4d0a580e-7ab3-4106-a846-9d4148e6230c")).toBe(true);
    expect(isBuildSessionId("ses_abc123")).toBe(false);
  });

  it("reads the latest tool line from stream items", () => {
    expect(
      activityFromStreamItems([
        {
          type: "tool_call",
          id: "1",
          toolCall: {
            id: "1",
            kind: "read",
            title: "Reading",
            description: "old.md",
            command: "",
            status: "completed",
            rawOutput: "",
          },
        },
        {
          type: "tool_call",
          id: "2",
          toolCall: {
            id: "2",
            kind: "edit",
            title: "Writing",
            description: "pipeline.csv",
            command: "",
            status: "in_progress",
            rawOutput: "",
          },
        },
      ])
    ).toBe("pipeline.csv");
  });

  it("falls back to lastActivity when the turn is empty", () => {
    const subagent: SubagentState = {
      sessionId: "child",
      parentToolCallId: "lane-task-lane:literature",
      subagentType: "literature",
      name: "Literature",
      status: "running",
      lastActivity: "Fetching nct.gov",
      turns: [
        {
          prompt: "",
          toolCalls: [],
          thinking: null,
          response: null,
          streamItems: [],
        },
      ],
      startedAt: 1,
      completedAt: null,
    };
    expect(latestSubagentActivity(subagent)).toBe("Fetching nct.gov");
  });

  it("maps specialist status to tool and subagent status", () => {
    expect(specialistUiStatus("succeeded")).toEqual({
      tool: "completed",
      subagent: "done",
    });
    expect(specialistUiStatus("running")).toEqual({
      tool: "in_progress",
      subagent: "running",
    });
  });
});
