import { useBuildSessionStore } from "@/app/craft/hooks/useBuildSessionStore";
import type { CraftJobSpecialistResponse } from "@/app/craft/services/apiServices";
import type { StreamItem } from "@/app/craft/types/displayTypes";

const PARENT = "parent-session";
const CHILD = "4d0a580e-7ab3-4106-a846-9d4148e6230c";

describe("syncJobSpecialists and hydrateSubagentFromMessages", () => {
  beforeEach(() => {
    useBuildSessionStore.setState({
      currentSessionId: null,
      sessions: new Map(),
    } as never);
  });

  it("seeds every lane role and patches the parent task card", () => {
    useBuildSessionStore.getState().createSession(PARENT, {
      status: "active",
      isLoaded: true,
      messages: [
        {
          id: "m1",
          type: "assistant",
          content: "",
          timestamp: new Date(),
          message_metadata: {
            streamItems: [
              {
                type: "tool_call",
                id: "lane-task-lane:literature",
                toolCall: {
                  id: "lane-task-lane:literature",
                  kind: "task",
                  title: "Literature",
                  description: "Literature — notes.md",
                  command: "",
                  status: "in_progress",
                  rawOutput: "",
                },
              },
            ] satisfies StreamItem[],
          },
        },
      ],
    });

    const specialists: CraftJobSpecialistResponse[] = [
      {
        id: "spec-1",
        session_id: CHILD,
        role: "literature",
        status: "running",
        node_id: "lane:literature",
        last_activity: "Fetching nct.gov",
      },
    ];
    useBuildSessionStore.getState().syncJobSpecialists(PARENT, specialists);

    const session = useBuildSessionStore.getState().sessions.get(PARENT);
    const subagent = session?.subagents.get(CHILD);
    expect(subagent?.subagentType).toBe("literature");
    expect(subagent?.name).toBe("Literature — notes.md");
    expect(subagent?.lastActivity).toBe("Fetching nct.gov");
    expect(subagent?.parentToolCallId).toBe("lane-task-lane:literature");
    const item = session?.messages[0]?.message_metadata?.streamItems?.[0] as
      | StreamItem
      | undefined;
    expect(item?.type === "tool_call" && item.toolCall.subagentSessionId).toBe(
      CHILD
    );
  });

  it("patches a status-suffixed card without binding researcher-2", () => {
    const otherChild = "55b05a82-5e0b-4d98-8059-9abe0f49686e";
    useBuildSessionStore.getState().createSession(PARENT, {
      status: "active",
      isLoaded: true,
      messages: [
        {
          id: "m-old",
          type: "assistant",
          content: "",
          timestamp: new Date(),
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
              {
                type: "tool_call",
                id: "lane-task-lane:researcher-2-in_progress",
                toolCall: {
                  id: "lane-task-lane:researcher-2-in_progress",
                  kind: "task",
                  title: "Researcher",
                  description: "Researcher — pipeline.csv",
                  command: "",
                  status: "in_progress",
                  rawOutput: "",
                },
              },
            ] satisfies StreamItem[],
          },
        },
      ],
    });

    useBuildSessionStore.getState().syncJobSpecialists(PARENT, [
      {
        id: "spec-r1",
        session_id: CHILD,
        role: "researcher",
        status: "running",
        node_id: "lane:researcher",
        last_activity: "Fetching nct.gov",
      },
      {
        id: "spec-r2",
        session_id: otherChild,
        role: "researcher",
        status: "running",
        node_id: "lane:researcher-2",
        last_activity: "Writing pipeline.csv",
      },
    ]);

    const items = useBuildSessionStore.getState().sessions.get(PARENT)
      ?.messages[0]?.message_metadata?.streamItems as StreamItem[] | undefined;
    const first = items?.[0];
    const second = items?.[1];
    expect(first?.type === "tool_call" && first.toolCall.id).toBe(
      "lane-task-lane:researcher-in_progress"
    );
    expect(
      first?.type === "tool_call" && first.toolCall.subagentSessionId
    ).toBe(CHILD);
    expect(second?.type === "tool_call" && second.toolCall.id).toBe(
      "lane-task-lane:researcher-2-in_progress"
    );
    expect(
      second?.type === "tool_call" && second.toolCall.subagentSessionId
    ).toBe(otherChild);
    const session = useBuildSessionStore.getState().sessions.get(PARENT);
    expect(session?.subagents.get(CHILD)?.name).toBe("Researcher — epi.md");
    expect(session?.subagents.get(otherChild)?.name).toBe(
      "Researcher — pipeline.csv"
    );
  });

  it("settles leftover running lane cards when the job is cancelled", () => {
    useBuildSessionStore.getState().createSession(PARENT, {
      status: "active",
      isLoaded: true,
      messages: [
        {
          id: "m-cancel",
          type: "assistant",
          content: "",
          timestamp: new Date(),
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
            ] satisfies StreamItem[],
          },
        },
      ],
    });
    useBuildSessionStore.getState().syncJobSpecialists(
      PARENT,
      [
        {
          id: "spec-r1",
          session_id: CHILD,
          role: "researcher",
          status: "failed",
          node_id: "lane:researcher",
          last_activity: "Cancelled",
        },
      ],
      "cancelled"
    );
    const item = useBuildSessionStore.getState().sessions.get(PARENT)
      ?.messages[0]?.message_metadata?.streamItems?.[0] as
      | StreamItem
      | undefined;
    expect(item?.type === "tool_call" && item.toolCall.status).toBe(
      "cancelled"
    );
    expect(
      useBuildSessionStore.getState().sessions.get(PARENT)?.subagents.get(CHILD)
        ?.status
    ).toBe("failed");
  });

  it("keeps cancelled researcher cards in the old turn after continue", () => {
    const newChild = "6c1f91d0-2a44-4f0f-9d1a-0b8f2e4c7a11";
    useBuildSessionStore.getState().createSession(PARENT, {
      status: "running",
      isLoaded: true,
      messages: [
        {
          id: "m-old",
          type: "assistant",
          content: "",
          timestamp: new Date(),
          message_metadata: {
            streamItems: [
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
                  subagentSessionId: CHILD,
                },
              },
            ] satisfies StreamItem[],
          },
        },
        {
          id: "m-continue",
          type: "user",
          content: "继续",
          timestamp: new Date(),
        },
      ],
    });
    useBuildSessionStore
      .getState()
      .seedSubagentMeta(
        PARENT,
        CHILD,
        "lane-task-lane:researcher",
        "researcher",
        "Researcher — epi.md",
        ""
      );
    useBuildSessionStore.getState().syncJobSpecialists(
      PARENT,
      [
        {
          id: "spec-new",
          session_id: newChild,
          role: "researcher",
          status: "running",
          node_id: "lane:researcher",
          last_activity: "Reading NOTES.md",
        },
      ],
      "running",
      "job-2"
    );

    const session = useBuildSessionStore.getState().sessions.get(PARENT);
    const oldItem = session?.messages[0]?.message_metadata?.streamItems?.[0] as
      | StreamItem
      | undefined;
    expect(oldItem?.type === "tool_call" && oldItem.toolCall.status).toBe(
      "cancelled"
    );
    expect(
      oldItem?.type === "tool_call" && oldItem.toolCall.subagentSessionId
    ).toBe(CHILD);
    const live = session?.streamItems[0];
    expect(live?.type === "tool_call" && live.toolCall.subagentSessionId).toBe(
      newChild
    );
    expect(live?.type === "tool_call" && live.toolCall.status).toBe(
      "in_progress"
    );
    expect(session?.subagents.get(CHILD)?.status).toBe("failed");
    expect(session?.subagents.get(newChild)?.status).toBe("running");
  });

  it("does not put finished lane cards on the live stream", () => {
    useBuildSessionStore.getState().createSession(PARENT, {
      status: "active",
      isLoaded: true,
      streamItems: [
        {
          type: "tool_call",
          id: "lane-task-lane:researcher",
          toolCall: {
            id: "lane-task-lane:researcher",
            kind: "task",
            title: "Researcher",
            description: "Researcher",
            command: "",
            status: "completed",
            rawOutput: "",
            subagentSessionId: CHILD,
          },
        },
      ],
      messages: [
        {
          id: "u1",
          type: "user",
          content: "go",
          timestamp: new Date(),
        },
        {
          id: "a1",
          type: "assistant",
          content: "done",
          timestamp: new Date(),
        },
      ],
    });
    useBuildSessionStore.getState().syncJobSpecialists(
      PARENT,
      [
        {
          id: "spec-1",
          session_id: CHILD,
          role: "researcher",
          status: "succeeded",
          node_id: "lane:researcher",
          last_activity: "Done",
        },
      ],
      "cancelled"
    );
    expect(
      useBuildSessionStore.getState().sessions.get(PARENT)?.streamItems
    ).toEqual([]);
  });

  it("hydrates a lane transcript from specialist messages", () => {
    useBuildSessionStore.getState().createSession(PARENT, {
      status: "active",
      isLoaded: true,
    });
    useBuildSessionStore
      .getState()
      .seedSubagentMeta(
        PARENT,
        CHILD,
        "lane-task-lane:clinical",
        "clinical",
        "Clinical",
        ""
      );
    useBuildSessionStore.getState().hydrateSubagentFromMessages(PARENT, CHILD, [
      {
        id: "c1",
        type: "assistant",
        content: "",
        timestamp: new Date(),
        message_metadata: {
          streamItems: [
            {
              type: "tool_call",
              id: "read-1",
              toolCall: {
                id: "read-1",
                kind: "read",
                title: "Reading",
                description: "readouts.csv",
                command: "",
                status: "completed",
                rawOutput: "ok",
              },
            },
          ],
        },
      },
    ]);

    const subagent = useBuildSessionStore
      .getState()
      .sessions.get(PARENT)
      ?.subagents.get(CHILD);
    expect(subagent?.lastActivity).toBe("readouts.csv");
    expect(subagent?.turns[0]?.streamItems).toHaveLength(1);
  });
});
