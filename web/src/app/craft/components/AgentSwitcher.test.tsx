import { fireEvent, render, screen } from "@tests/setup/test-utils";
import AgentSwitcher from "@/app/craft/components/AgentSwitcher";
import { useBuildSessionStore } from "@/app/craft/hooks/useBuildSessionStore";
import type { CraftJobSpecialistResponse } from "@/app/craft/services/apiServices";
import type { StreamItem } from "@/app/craft/types/displayTypes";

const PARENT = "parent-session";
const CHILD_ONE = "4d0a580e-7ab3-4106-a846-9d4148e6230c";
const CHILD_TWO = "55b05a82-5e0b-4d98-8059-9abe0f49686e";

function laneCard(
  id: string,
  description: string
): Extract<StreamItem, { type: "tool_call" }> {
  return {
    type: "tool_call",
    id,
    toolCall: {
      id,
      kind: "task",
      title: "Researcher",
      description,
      command: "",
      status: "in_progress",
      rawOutput: "",
    },
  };
}

describe("AgentSwitcher", () => {
  beforeEach(() => {
    useBuildSessionStore.setState({
      currentSessionId: null,
      sessions: new Map(),
      sessionHistory: [],
    } as never);
  });

  it("opens a specialist transcript from the header menu", () => {
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
              laneCard(
                "lane-task-lane:researcher-in_progress",
                "Researcher — outputs/normalized/epi.md"
              ),
              laneCard(
                "lane-task-lane:researcher-2-in_progress",
                "Researcher — outputs/normalized/pipeline.csv"
              ),
            ],
          },
        },
      ],
    });
    useBuildSessionStore.getState().setCurrentSession(PARENT);
    useBuildSessionStore.setState({
      sessionHistory: [
        {
          id: PARENT,
          title: "HMPL-760",
          createdAt: new Date(),
          projectId: null,
        },
      ],
    });

    const specialists: CraftJobSpecialistResponse[] = [
      {
        id: "spec-r1",
        session_id: CHILD_ONE,
        role: "researcher",
        status: "running",
        node_id: "lane:researcher",
        last_activity: "Fetching nct.gov",
      },
      {
        id: "spec-r2",
        session_id: CHILD_TWO,
        role: "researcher",
        status: "running",
        node_id: "lane:researcher-2",
        last_activity: "Writing pipeline.csv",
      },
    ];
    useBuildSessionStore.getState().syncJobSpecialists(PARENT, specialists);

    render(<AgentSwitcher />);
    fireEvent.click(screen.getByRole("button", { name: "Switch agent" }));
    fireEvent.pointerDown(
      screen.getByRole("button", { name: /pipeline\.csv/ })
    );

    expect(
      useBuildSessionStore.getState().sessions.get(PARENT)
        ?.viewedSubagentSessionId
    ).toBe(CHILD_TWO);
  });
});
