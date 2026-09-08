/**
 * @jest-environment jsdom
 */
import { render, screen, setupUser } from "@tests/setup/test-utils";
import { CraftAskBar } from "@/app/craft/components/CraftAskBar";
import type { CraftJobResponse } from "@/app/craft/services/apiServices";

function job(kind: string): CraftJobResponse {
  return {
    id: "job-1",
    session_id: "session-1",
    project_id: null,
    scenario_id: null,
    name: "GLP-1 report",
    domain: "biomed",
    status: "interrupted",
    current_phase_index: 0,
    phases: [],
    total_budget_seconds: 7200,
    phase_budget_seconds: 1500,
    error_detail: null,
    specialists: [],
    interrupt: {
      kind,
      payload: { goal: "GLP-1", summary: "Proposed next steps for: GLP-1", steps: ["Literature"] },
    },
  };
}

describe("CraftAskBar", () => {
  it("shows start chips for a plan interrupt", async () => {
    const user = setupUser();
    const onJobAction = jest.fn();
    render(
      <CraftAskBar job={job("approve_plan")} onJobAction={onJobAction} />
    );

    expect(screen.getByTestId("craft-ask-bar")).toBeInTheDocument();
    expect(screen.getByTestId("craft-ask-approve")).toHaveTextContent("Start");
    expect(screen.getByText(/Proposed next steps/)).toBeInTheDocument();
    await user.click(screen.getByTestId("craft-ask-approve"));
    expect(onJobAction).toHaveBeenCalledWith("approve");
  });

  it("shows accept chips for a delivery interrupt", () => {
    render(<CraftAskBar job={job("approve_delivery")} onJobAction={jest.fn()} />);
    expect(screen.getByTestId("craft-ask-approve")).toHaveTextContent("Accept");
    expect(screen.getByTestId("craft-ask-revise")).toHaveTextContent(
      "Request changes"
    );
  });

  it("shows question chips above host HITL", async () => {
    const user = setupUser();
    const onQuestionAnswer = jest.fn();
    render(
      <CraftAskBar
        job={job("approve_plan")}
        question={{
          requestId: "q1",
          prompt: "Which indication first?",
          options: ["Obesity", "T2D"],
        }}
        onQuestionAnswer={onQuestionAnswer}
      />
    );
    expect(screen.getByText("Which indication first?")).toBeInTheDocument();
    await user.click(screen.getByText("Obesity"));
    expect(onQuestionAnswer).toHaveBeenCalledWith("q1", true, [["Obesity"]]);
  });

  it("walks through two questions before submitting", async () => {
    const user = setupUser();
    const onQuestionAnswer = jest.fn();
    render(
      <CraftAskBar
        question={{
          requestId: "q2",
          prompt: "Which modality?",
          options: ["Oral", "Injection"],
          questions: [
            { prompt: "Which modality?", options: ["Oral", "Injection"] },
            { prompt: "Which indication first?", options: ["Obesity", "T2D"] },
          ],
        }}
        onQuestionAnswer={onQuestionAnswer}
      />
    );
    expect(screen.getByText("Which modality?")).toBeInTheDocument();
    await user.click(screen.getByText("Oral"));
    expect(onQuestionAnswer).not.toHaveBeenCalled();
    expect(screen.getByText("Which indication first?")).toBeInTheDocument();
    await user.click(screen.getByText("Obesity"));
    expect(onQuestionAnswer).toHaveBeenCalledWith("q2", true, [
      ["Oral"],
      ["Obesity"],
    ]);
  });

  it("rejects from the reject chip", async () => {
    const user = setupUser();
    const onQuestionAnswer = jest.fn();
    render(
      <CraftAskBar
        question={{
          requestId: "q3",
          prompt: "Which indication first?",
          options: ["Obesity", "T2D"],
        }}
        onQuestionAnswer={onQuestionAnswer}
      />
    );
    await user.click(screen.getByTestId("craft-ask-reject"));
    expect(onQuestionAnswer).toHaveBeenCalledWith("q3", false);
  });

  it("treats a cancel option as deny", async () => {
    const user = setupUser();
    const onQuestionAnswer = jest.fn();
    render(
      <CraftAskBar
        question={{
          requestId: "q4",
          prompt: "Retry search?",
          options: ["Retry search", "Cancel"],
        }}
        onQuestionAnswer={onQuestionAnswer}
      />
    );
    await user.click(screen.getByText("Cancel"));
    expect(onQuestionAnswer).toHaveBeenCalledWith("q4", false);
  });
});
