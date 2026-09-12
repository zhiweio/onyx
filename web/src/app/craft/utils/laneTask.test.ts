import {
  childSessionIdForTask,
  filenameFromLaneLabel,
  isGenericRoleLabel,
  lastUserMessageIndex,
  laneTaskCardLabel,
  laneTaskNodeIdFromToolId,
  laneTaskToolId,
  matchesLaneTaskToolId,
  patchLaneTaskToolCalls,
  pinForeignLaneTaskCards,
  settleOpenLaneTaskCards,
  settleTranscriptForJobStatus,
  subagentSwitcherLabel,
  taskRowStatus,
} from "@/app/craft/utils/laneTask";

describe("laneTask ids", () => {
  it("keeps a stable id that does not include status", () => {
    expect(laneTaskToolId("lane:researcher")).toBe("lane-task-lane:researcher");
    expect(laneTaskNodeIdFromToolId("lane-task-lane:researcher")).toBe(
      "lane:researcher"
    );
    expect(
      laneTaskNodeIdFromToolId("lane-task-lane:researcher-in_progress")
    ).toBe("lane:researcher");
  });

  it("does not bind researcher to researcher-2", () => {
    expect(
      matchesLaneTaskToolId(
        "lane-task-lane:researcher-in_progress",
        "lane-task-lane:researcher"
      )
    ).toBe(true);
    expect(
      matchesLaneTaskToolId(
        "lane-task-lane:researcher-2-in_progress",
        "lane-task-lane:researcher"
      )
    ).toBe(false);
    expect(
      matchesLaneTaskToolId(
        "lane-task-lane:researcher-2-in_progress",
        "lane-task-lane:researcher-2"
      )
    ).toBe(true);
  });

  it("resolves a child session from an old status-suffixed card", () => {
    const childId = "4d0a580e-7ab3-4106-a846-9d4148e6230c";
    expect(
      childSessionIdForTask(
        "lane-task-lane:researcher-in_progress",
        undefined,
        [
          {
            sessionId: childId,
            parentToolCallId: "lane-task-lane:researcher",
          },
        ]
      )
    ).toBe(childId);
  });
});

describe("lane task labels", () => {
  it("reads a deliverable file name from the card text", () => {
    expect(
      filenameFromLaneLabel("Researcher — outputs/normalized/market-access.md")
    ).toBe("market-access.md");
    expect(filenameFromLaneLabel("Writing pipeline.csv")).toBe("pipeline.csv");
    expect(filenameFromLaneLabel("Researcher")).toBe("");
  });

  it("treats a title-cased role as a generic label", () => {
    expect(isGenericRoleLabel("Researcher", "researcher")).toBe(true);
    expect(isGenericRoleLabel("Researcher — epi.md", "researcher")).toBe(false);
  });

  it("reads the card description for a status-suffixed tool id", () => {
    expect(
      laneTaskCardLabel(
        [
          {
            type: "tool_call",
            id: "lane-task-lane:researcher-in_progress",
            toolCall: {
              id: "lane-task-lane:researcher-in_progress",
              title: "Researcher",
              description: "Researcher — outputs/normalized/epi.md",
            },
          },
        ],
        "lane-task-lane:researcher"
      )
    ).toBe("Researcher — outputs/normalized/epi.md");
  });

  it("shortens the switcher title to the deliverable file", () => {
    expect(
      subagentSwitcherLabel(
        "Researcher — outputs/normalized/market-access.md",
        "researcher",
        "Let me understand the task"
      )
    ).toBe("market-access.md");
    expect(
      subagentSwitcherLabel("Researcher", "researcher", "Writing pipeline.csv")
    ).toBe("pipeline.csv");
    expect(subagentSwitcherLabel("Map the tool cards", "explore")).toBe(
      "Map the tool cards"
    );
  });

  it("settles an open lane-task card when the job is cancelled", () => {
    const settled = settleOpenLaneTaskCards(
      [
        {
          type: "tool_call",
          id: "lane-task-lane:researcher-in_progress",
          toolCall: {
            id: "lane-task-lane:researcher-in_progress",
            kind: "task",
            title: "Researcher",
            description: "Researcher — epi.md",
            command: "",
            status: "in_progress",
            rawOutput: "",
          },
        },
      ],
      "cancelled"
    );
    expect(settled[0]?.type === "tool_call" && settled[0].toolCall.status).toBe(
      "cancelled"
    );
  });

  it("settles leftover lane cards in saved messages for a cancelled job", () => {
    const { messages, streamItems } = settleTranscriptForJobStatus(
      [
        {
          message_metadata: {
            streamItems: [
              {
                type: "tool_call",
                id: "lane-task-lane:researcher-in_progress",
                toolCall: {
                  id: "lane-task-lane:researcher-in_progress",
                  kind: "task",
                  title: "Researcher",
                  description: "Researcher — epi.md",
                  command: "",
                  status: "in_progress",
                  rawOutput: "",
                },
              },
            ],
          },
        },
      ],
      [],
      "cancelled"
    );
    const item = messages[0]?.message_metadata?.streamItems?.[0];
    expect(item?.type === "tool_call" && item.toolCall.status).toBe(
      "cancelled"
    );
    expect(streamItems).toEqual([]);
  });

  it("treats a cancelled job card as failed in the row", () => {
    expect(
      taskRowStatus("running", "in_progress", "running", "cancelled")
    ).toBe("failed");
    expect(taskRowStatus("running", "cancelled")).toBe("failed");
    expect(taskRowStatus("done", "in_progress", "succeeded", "cancelled")).toBe(
      "done"
    );
  });

  it("does not revive a settled card when a new specialist syncs", () => {
    const patched = patchLaneTaskToolCalls(
      [
        {
          type: "tool_call",
          id: "lane-task-lane:researcher",
          toolCall: {
            id: "lane-task-lane:researcher",
            kind: "task",
            title: "Researcher",
            description: "Researcher — epi.md",
            command: "",
            status: "cancelled",
            rawOutput: "",
            subagentSessionId: "old-child",
          },
        },
      ],
      "lane-task-lane:researcher",
      {
        status: "in_progress",
        subagentSessionId: "new-child",
      },
      true
    );
    expect(patched[0]?.type === "tool_call" && patched[0].toolCall.status).toBe(
      "cancelled"
    );
    expect(
      patched[0]?.type === "tool_call" && patched[0].toolCall.subagentSessionId
    ).toBe("old-child");
  });

  it("pins leftover cards that belong to another specialist session", () => {
    const pinned = pinForeignLaneTaskCards(
      [
        {
          type: "tool_call",
          id: "lane-task-lane:researcher",
          toolCall: {
            id: "lane-task-lane:researcher",
            kind: "task",
            title: "Researcher",
            description: "Researcher — epi.md",
            command: "",
            status: "in_progress",
            rawOutput: "",
            subagentSessionId: "old-child",
          },
        },
      ],
      new Set(["new-child"])
    );
    expect(pinned[0]?.type === "tool_call" && pinned[0].toolCall.status).toBe(
      "cancelled"
    );
  });

  it("finds the last visible user message", () => {
    expect(
      lastUserMessageIndex([
        { type: "assistant" },
        { type: "user" },
        { type: "assistant" },
        { type: "user" },
        { type: "assistant" },
      ])
    ).toBe(3);
  });
});
