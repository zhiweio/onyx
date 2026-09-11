import {
  classifyToolPhase,
  foldTurnStream,
  shortPhaseTarget,
  stepSummary,
} from "@/lib/craft/foldTurnStream";
import type { StreamItem, ToolCallState } from "@/app/craft/types/displayTypes";

function tool(
  overrides: Partial<ToolCallState> & Pick<ToolCallState, "id" | "kind">
): ToolCallState {
  return {
    title: "Reading",
    description: overrides.description ?? "file.md",
    command: "",
    status: "completed",
    rawOutput: "",
    ...overrides,
  };
}

function thinking(
  id: string,
  content: string,
  isStreaming = false
): StreamItem {
  return { type: "thinking", id, content, isStreaming };
}

function text(id: string, content: string, isStreaming = false): StreamItem {
  return { type: "text", id, content, isStreaming };
}

function toolItem(state: ToolCallState): StreamItem {
  return { type: "tool_call", id: state.id, toolCall: state };
}

describe("classifyToolPhase", () => {
  it("maps explore-type tasks to explore", () => {
    expect(
      classifyToolPhase(
        tool({
          id: "t1",
          kind: "task",
          toolName: "task",
          subagentType: "explore",
        })
      )
    ).toBe("explore");
  });
});

describe("foldTurnStream", () => {
  it("merges adjacent thoughts and splits after a tool batch", () => {
    const folded = foldTurnStream(
      [
        thinking("th1", "first"),
        thinking("th2", "second"),
        toolItem(tool({ id: "r1", kind: "read", description: "a.md" })),
        thinking("th3", "third"),
        text("a1", "Done"),
      ],
      { isStreaming: false }
    );
    expect(folded.rows.map((row) => row.kind)).toEqual([
      "thought",
      "tools",
      "thought",
    ]);
    const first = folded.rows[0];
    expect(first?.kind).toBe("thought");
    if (first?.kind === "thought") {
      expect(first.content).toContain("first");
      expect(first.content).toContain("second");
    }
    expect(folded.answer?.content).toBe("Done");
    expect(folded.showPlanningNext).toBe(false);
  });

  it("does not split an explore batch on thinking", () => {
    const folded = foldTurnStream(
      [
        toolItem(tool({ id: "r1", kind: "read", description: "a.md" })),
        thinking("th1", "mid"),
        toolItem(tool({ id: "r2", kind: "read", description: "b.md" })),
      ],
      { isStreaming: false }
    );
    expect(folded.rows.map((row) => row.kind)).toEqual(["tools", "thought"]);
    const toolsRow = folded.rows[0];
    expect(toolsRow?.kind).toBe("tools");
    if (toolsRow?.kind === "tools") {
      expect(toolsRow.phase).toBe("explore");
      expect(toolsRow.tools.map((item) => item.id)).toEqual(["r1", "r2"]);
    }
  });

  it("starts a new Explored group after an edit", () => {
    const folded = foldTurnStream(
      [
        toolItem(tool({ id: "r1", kind: "read", description: "a.md" })),
        toolItem(
          tool({
            id: "e1",
            kind: "edit",
            toolName: "write",
            title: "Writing",
            description: "out.md",
          })
        ),
        toolItem(tool({ id: "r2", kind: "read", description: "b.md" })),
      ],
      { isStreaming: false }
    );
    const phases = folded.rows
      .filter((row) => row.kind === "tools")
      .map((row) => (row.kind === "tools" ? row.phase : null));
    expect(phases).toEqual(["explore", "edit", "explore"]);
  });

  it("treats trailing text as the answer and mid-turn text as a step summary", () => {
    const folded = foldTurnStream(
      [
        toolItem(tool({ id: "r1", kind: "read" })),
        text("mid", "still working"),
        toolItem(
          tool({
            id: "e1",
            kind: "edit",
            toolName: "write",
            description: "out.md",
          })
        ),
        text("ans", "Here is the report"),
      ],
      { isStreaming: false }
    );
    expect(folded.answer?.content).toBe("Here is the report");
    expect(folded.rows.some((row) => row.kind === "text")).toBe(false);
    const explore = folded.rows[0];
    expect(explore?.kind).toBe("tools");
    if (explore?.kind === "tools") {
      expect(explore.summary).toBe("still working");
    }
  });

  it("adds a thought preview and prefers following commentary", () => {
    const folded = foldTurnStream(
      [
        thinking("th1", "Load the skill and map the workspace. Then fetch NCT."),
        toolItem(tool({ id: "r1", kind: "read", description: "SKILL.md" })),
        text("mid", "Skill is loaded. Next I will fetch the trial."),
        toolItem(
          tool({
            id: "e1",
            kind: "edit",
            toolName: "write",
            description: "out.md",
          })
        ),
        text("ans", "Final answer"),
      ],
      { isStreaming: false }
    );
    const thought = folded.rows[0];
    const explore = folded.rows[1];
    expect(thought?.kind).toBe("thought");
    expect(explore?.kind).toBe("tools");
    if (thought?.kind === "thought") {
      expect(thought.summary).toBe("Load the skill and map the workspace.");
    }
    if (explore?.kind === "tools") {
      expect(explore.summary).toBe("Skill is loaded.");
    }
  });

  it("puts the next thought on the preceding run and does not repeat it", () => {
    const folded = foldTurnStream(
      [
        thinking("th1", "Load the skill and map the workspace."),
        toolItem(tool({ id: "r1", kind: "read", description: "SKILL.md" })),
        toolItem(
          tool({
            id: "x1",
            kind: "execute",
            command: "ls -la /very/long/path && echo one && echo two",
          })
        ),
        thinking(
          "th2",
          "The skill tool returned a very terse message, not the full skill."
        ),
        text("ans", "Final answer"),
      ],
      { isStreaming: false }
    );
    const kinds = folded.rows.map((row) => row.kind);
    expect(kinds).toEqual(["thought", "tools", "tools", "thought"]);
    const run = folded.rows[2];
    const nextThought = folded.rows[3];
    expect(run?.kind).toBe("tools");
    if (run?.kind === "tools") {
      expect(run.phase).toBe("run");
      expect(run.summary).toBe(
        "The skill tool returned a very terse message, not the full skill."
      );
    }
    expect(nextThought?.kind).toBe("thought");
    if (nextThought?.kind === "thought") {
      expect(nextThought.summary).toBeUndefined();
    }
  });

  it("shows planning next only in a live settled gap", () => {
    const settled: StreamItem[] = [
      thinking("th1", "done thinking", false),
    ];
    expect(foldTurnStream(settled, { isStreaming: true }).showPlanningNext).toBe(
      true
    );
    expect(
      foldTurnStream(
        [thinking("th1", "still", true)],
        { isStreaming: true }
      ).showPlanningNext
    ).toBe(false);
    expect(foldTurnStream(settled, { isStreaming: false }).showPlanningNext).toBe(
      false
    );
    expect(
      foldTurnStream([...settled, text("a", "Answer")], { isStreaming: true })
        .showPlanningNext
    ).toBe(false);
  });
});

describe("stepSummary", () => {
  it("keeps the first sentence and shortens long text", () => {
    expect(stepSummary("Load the skill. Then fetch NCT.")).toBe(
      "Load the skill."
    );
    expect(stepSummary("先读技能，再拉试验。然后写报告。")).toBe(
      "先读技能，再拉试验。"
    );
    const long = `${"word ".repeat(80)}.`;
    expect(stepSummary(long).endsWith("…")).toBe(true);
    expect(stepSummary(long).length).toBeLessThanOrEqual(160);
  });

  it("skips filler and uses the next useful sentence", () => {
    expect(stepSummary("Interesting.")).toBe("");
    expect(
      stepSummary("Good. I have the skill loaded and will fetch the trial.")
    ).toBe("I have the skill loaded and will fetch the trial.");
  });
});

describe("shortPhaseTarget", () => {
  it("keeps a short label and uses the basename of a long path", () => {
    expect(shortPhaseTarget("SKILL.md")).toBe("SKILL.md");
    expect(
      shortPhaseTarget(
        "outputs/markdown/very/long/nested/HMPL760_1L_DLBCL_立项评估.md"
      )
    ).toBe("HMPL760_1L_DLBCL_立项评估.md");
    expect(shortPhaseTarget("ls -la; echo one; echo two; echo three; echo four; echo five")).toContain(
      "…"
    );
  });
});
