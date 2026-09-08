import {
  compactJobError,
  isDurabilityFileTool,
  isHiddenJobTool,
  isHostContinueMessage,
  jobErrorDisplay,
  jobStatusTagColor,
  phaseTagColor,
  specialistRoleKey,
} from "@/lib/craft-jobs/display";
import type { ToolCallState } from "@/app/craft/types/displayTypes";

describe("craft job display helpers", () => {
  it("compacts a failed-job wall of text", () => {
    expect(compactJobError("  a\n\nb  ")).toBe("a b");
    expect(compactJobError("x".repeat(300)).endsWith("...")).toBe(true);
    expect(compactJobError(null)).toBe("");
    expect(compactJobError("Phase gate retry limit reached:")).toBe(
      "Phase gate retry limit reached"
    );
    expect(
      compactJobError(
        '# PLAN\n{"goal":"write report","status":"pending"}\n外部网络出口被完全阻断 (403)\n'
      )
    ).toBe("外部网络出口被完全阻断 (403)");
    expect(jobErrorDisplay("Phase gate retry limit reached:", "Stopped")).toBe(
      "Phase gate retry limit reached"
    );
    expect(jobErrorDisplay("", "Stopped")).toBe("Stopped");
  });

  it("maps specialist roles and status colors", () => {
    expect(specialistRoleKey("lane:literature")).toBe("literature");
    expect(specialistRoleKey("CMC")).toBe("cmc");
    expect(specialistRoleKey("unknown")).toBeNull();
    expect(phaseTagColor("failed")).toBe("red");
    expect(jobStatusTagColor("interrupted")).toBe("amber");
  });

  it("hides durability file tools but keeps todowrite", () => {
    const writePlan: ToolCallState = {
      id: "1",
      kind: "edit",
      toolName: "write",
      title: "Writing",
      description: "outputs/PLAN.md",
      command: "",
      status: "completed",
      rawOutput: "",
    };
    const todos: ToolCallState = {
      ...writePlan,
      id: "2",
      toolName: "todowrite",
      description: "todos",
    };
    expect(isDurabilityFileTool(writePlan)).toBe(true);
    expect(isDurabilityFileTool(todos)).toBe(false);
  });

  it("hides mcp cache and cross-session bash, but keeps lane task cards", () => {
    const mcp: ToolCallState = {
      id: "3",
      kind: "read",
      toolName: "read",
      title: "Reading",
      description: "outputs/mcp/search.json",
      command: "",
      status: "completed",
      rawOutput: "",
    };
    const crossSession: ToolCallState = {
      id: "4",
      kind: "execute",
      toolName: "bash",
      title: "Running",
      description: "ls /workspace/sessions/83f40b37-7f00-41dd-b7db-fe5c0b426068",
      command: "ls /workspace/.opencode-data",
      status: "completed",
      rawOutput: "",
    };
    const laneTask: ToolCallState = {
      id: "5",
      kind: "task",
      toolName: "task",
      title: "Literature",
      description: "Literature — outputs/lanes/literature/NOTES.md",
      command: "",
      status: "completed",
      rawOutput: "",
    };
    expect(isHiddenJobTool(mcp)).toBe(true);
    expect(isHiddenJobTool(crossSession)).toBe(true);
    expect(isHiddenJobTool(laneTask)).toBe(false);
    expect(
      isHostContinueMessage({ craft_job_continue: true, type: "user_message" })
    ).toBe(true);
    expect(isHostContinueMessage({ type: "user_message" })).toBe(false);
  });
});
