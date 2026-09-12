import { fireEvent, render, screen } from "@tests/setup/test-utils";
import TaskBody from "@/app/craft/components/tool-cards/TaskBody";
import { useBuildSessionStore } from "@/app/craft/hooks/useBuildSessionStore";
import type { CraftJobResponse } from "@/app/craft/services/apiServices";
import type { ToolCallState } from "@/app/craft/types/displayTypes";

jest.mock("@/app/craft/hooks/useLaneTranscript", () => ({
  useLaneTranscript: jest.fn(),
}));

const craftJobRef: { current: CraftJobResponse | null } = { current: null };

jest.mock("@/app/craft/components/CraftJobBanner", () => ({
  useCraftJob: () => ({ data: craftJobRef.current }),
}));

function task(overrides: Partial<ToolCallState>): ToolCallState {
  return {
    id: "task-1",
    kind: "task",
    toolName: "task",
    title: "Explore",
    description: "Map the tool cards",
    command: "",
    status: "in_progress",
    rawOutput: "",
    ...overrides,
  };
}

describe("TaskBody", () => {
  beforeEach(() => {
    craftJobRef.current = null;
    useBuildSessionStore.setState({
      currentSessionId: null,
      sessions: new Map(),
    } as never);
  });

  it("does not expand when no child session is linked", () => {
    render(<TaskBody toolCall={task({})} />);
    expect(
      screen.queryByRole("button", { name: /expand/i })
    ).not.toBeInTheDocument();
    expect(screen.getByText("Map the tool cards")).toBeInTheDocument();
  });

  it("expands a running explore subagent and shows a waiting line", () => {
    const sessionId = "parent-session";
    const childId = "child-explore";
    useBuildSessionStore.getState().createSession(sessionId, {
      status: "active",
      isLoaded: true,
    });
    useBuildSessionStore.getState().setCurrentSession(sessionId);
    useBuildSessionStore
      .getState()
      .seedSubagentMeta(sessionId, childId, "task-1", "explore", "Explore", "");

    render(
      <TaskBody
        toolCall={task({
          subagentType: "explore",
          subagentSessionId: childId,
        })}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: /expand/i }));
    expect(screen.getByText("Waiting for the first step")).toBeInTheDocument();
  });

  it("shows live tool lines for a literature lane", () => {
    const sessionId = "parent-session";
    const childId = "55b05a82-5e0b-4d98-8059-9abe0f49686e";
    useBuildSessionStore.getState().createSession(sessionId, {
      status: "active",
      isLoaded: true,
    });
    useBuildSessionStore.getState().setCurrentSession(sessionId);
    useBuildSessionStore
      .getState()
      .seedSubagentMeta(
        sessionId,
        childId,
        "lane-task-lane:literature",
        "literature",
        "Literature",
        ""
      );
    useBuildSessionStore.getState().recordSubagentToolCall(
      sessionId,
      childId,
      "lane-task-lane:literature",
      {
        id: "bash-1",
        kind: "execute",
        toolName: "bash",
        title: "Running command",
        description: "outputs/normalized/pipeline.csv",
        command: "ls",
        status: "in_progress",
        rawOutput: "",
      },
      "literature",
      "Literature"
    );

    render(
      <TaskBody
        toolCall={task({
          id: "lane-task-lane:literature",
          title: "Literature",
          description: "Literature — outputs/normalized/pipeline.csv",
          subagentType: "literature",
          subagentSessionId: childId,
        })}
      />
    );

    expect(
      screen.getByText("outputs/normalized/pipeline.csv")
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /expand/i }));
    expect(screen.getByText("Running")).toBeInTheDocument();
  });

  it("expands an old status-suffixed lane card from the specialist map", () => {
    const sessionId = "parent-session";
    const childId = "4d0a580e-7ab3-4106-a846-9d4148e6230c";
    useBuildSessionStore.getState().createSession(sessionId, {
      status: "active",
      isLoaded: true,
    });
    useBuildSessionStore.getState().setCurrentSession(sessionId);
    useBuildSessionStore
      .getState()
      .seedSubagentMeta(
        sessionId,
        childId,
        "lane-task-lane:researcher",
        "researcher",
        "Researcher",
        ""
      );

    render(
      <TaskBody
        toolCall={task({
          id: "lane-task-lane:researcher-in_progress",
          title: "Researcher",
          description: "Researcher — outputs/normalized/epi-patient-pool.md",
          subagentType: "researcher",
        })}
      />
    );

    expect(screen.getByRole("button", { name: /expand/i })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /expand/i }));
    expect(screen.getByText("Waiting for the first step")).toBeInTheDocument();
  });

  it("opens the full transcript from the expanded row", () => {
    const sessionId = "parent-session";
    const childId = "child-plan";
    useBuildSessionStore.getState().createSession(sessionId, {
      status: "active",
      isLoaded: true,
    });
    useBuildSessionStore.getState().setCurrentSession(sessionId);
    useBuildSessionStore
      .getState()
      .seedSubagentMeta(sessionId, childId, "task-1", "plan", "Plan", "");

    render(
      <TaskBody
        toolCall={task({
          subagentType: "plan",
          subagentSessionId: childId,
          description: "Draft rebase plan",
        })}
      />
    );
    fireEvent.click(screen.getByRole("button", { name: /expand/i }));
    fireEvent.click(screen.getByRole("button", { name: "Open" }));
    expect(
      useBuildSessionStore.getState().sessions.get(sessionId)
        ?.viewedSubagentSessionId
    ).toBe(childId);
  });

  it("does not keep a cancelled lane card in the running state", () => {
    const sessionId = "parent-session";
    const childId = "4d0a580e-7ab3-4106-a846-9d4148e6230c";
    useBuildSessionStore.getState().createSession(sessionId, {
      status: "active",
      isLoaded: true,
    });
    useBuildSessionStore.getState().setCurrentSession(sessionId);
    useBuildSessionStore
      .getState()
      .seedSubagentMeta(
        sessionId,
        childId,
        "lane-task-lane:researcher",
        "researcher",
        "Researcher",
        ""
      );

    render(
      <TaskBody
        toolCall={task({
          id: "lane-task-lane:researcher",
          subagentType: "researcher",
          subagentSessionId: childId,
          status: "cancelled",
          description: "Researcher — epi.md",
        })}
      />
    );

    expect(document.querySelector(".animate-spin")).toBeNull();
  });

  it("does not show a cancelled old row as running for a new job", () => {
    const sessionId = "parent-session";
    const oldChild = "4d0a580e-7ab3-4106-a846-9d4148e6230c";
    const newChild = "6c1f91d0-2a44-4f0f-9d1a-0b8f2e4c7a11";
    useBuildSessionStore.getState().createSession(sessionId, {
      status: "active",
      isLoaded: true,
    });
    useBuildSessionStore.getState().setCurrentSession(sessionId);
    useBuildSessionStore
      .getState()
      .seedSubagentMeta(
        sessionId,
        oldChild,
        "lane-task-lane:researcher",
        "researcher",
        "Researcher",
        ""
      );
    craftJobRef.current = {
      id: "job-2",
      session_id: sessionId,
      project_id: null,
      scenario_id: null,
      name: "HMPL-760",
      domain: "biopharma",
      status: "running",
      current_phase_index: 0,
      phases: [],
      total_budget_seconds: 0,
      phase_budget_seconds: 0,
      error_detail: null,
      specialists: [
        {
          id: "spec-new",
          session_id: newChild,
          role: "researcher",
          status: "running",
          node_id: "lane:researcher",
          last_activity: "Reading NOTES.md",
        },
      ],
    } as CraftJobResponse;

    render(
      <TaskBody
        toolCall={task({
          id: "lane-task-lane:researcher",
          subagentType: "researcher",
          subagentSessionId: oldChild,
          status: "cancelled",
          description: "Researcher — epi.md",
        })}
      />
    );

    expect(document.querySelector(".animate-spin")).toBeNull();
    expect(screen.queryByText("Reading NOTES.md")).not.toBeInTheDocument();
  });
});
