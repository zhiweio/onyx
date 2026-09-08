/**
 * @jest-environment jsdom
 */
import { render, screen, setupUser } from "@tests/setup/test-utils";
import { CraftJobBannerView } from "@/app/craft/components/CraftJobBanner";
import type { CraftJobResponse } from "@/app/craft/services/apiServices";

function failedJob(): CraftJobResponse {
  return {
    id: "09aa6f0b-2d51-4aa3-8939-610bc3dd90ba",
    session_id: "1eaf40af-003a-4f00-8144-ed99d2603945",
    project_id: null,
    scenario_id: null,
    name: "撰写一份 GLP-1 受体激动剂创新药立项深度研究报告",
    domain: "biomed",
    status: "failed",
    current_phase_index: 1,
    phases: [
      { id: "plan", name: "Plan", kind: "plan", status: "succeeded" },
      {
        id: "lanes",
        name: "Research",
        kind: "research_lane",
        status: "failed",
      },
    ],
    timeline: [
      { id: "plan", kind: "plan", status: "succeeded", label: "Plan" },
      {
        id: "lanes",
        kind: "research_lane",
        status: "failed",
        label: "Research",
      },
    ],
    total_budget_seconds: 7200,
    phase_budget_seconds: 1500,
    error_detail:
      '# PLAN — GLP-1\n{"goal":"撰写一份 GLP-1 报告","specialists":[{"id":"literature","status":"pending"}]}\n外部网络出口被完全阻断 (403)',
    specialists: [
      {
        id: "lit",
        session_id: "s-lit",
        role: "literature",
        status: "failed",
        error_detail: "webfetch 403 GET https://api.fda.gov/drug/label.json",
      },
      {
        id: "clin",
        session_id: "s-clin",
        role: "clinical",
        status: "pending",
      },
    ],
    artifacts: [
      {
        path: "outputs/plan/PLAN.json",
        summary:
          '# PLAN\n{"goal":"撰写一份","specialists":[{"status":"pending"}]}',
        producer_node: "plan",
      },
    ],
  };
}

function interruptedJob(): CraftJobResponse {
  return {
    ...failedJob(),
    status: "interrupted",
    error_detail: null,
    specialists: [],
    interrupt: { kind: "approve_plan", payload: { goal: "GLP-1" } },
  };
}

describe("CraftJobBannerView", () => {
  it("keeps a failed job collapsed until the chip is opened", async () => {
    const user = setupUser();
    render(
      <CraftJobBannerView data={failedJob()} onCancel={jest.fn()} />
    );

    expect(screen.getByTestId("craft-job-banner")).toBeInTheDocument();
    expect(screen.getByText("Long job")).toBeInTheDocument();
    expect(screen.getAllByText("Failed").length).toBeGreaterThan(0);
    expect(screen.queryByTestId("craft-job-error")).not.toBeInTheDocument();
    expect(screen.queryByText("Literature")).not.toBeInTheDocument();
    expect(screen.queryByText(/"status": "pending"/)).not.toBeInTheDocument();

    await user.click(screen.getByTestId("craft-job-banner"));

    expect(
      screen.getByText("撰写一份 GLP-1 受体激动剂创新药立项深度研究报告")
    ).toBeInTheDocument();
    expect(screen.getByText("biomed")).toBeInTheDocument();
    expect(screen.getByText("Literature")).toBeInTheDocument();
    expect(screen.getByText("Clinical")).toBeInTheDocument();
    expect(screen.getByTestId("craft-job-error")).toHaveTextContent(
      "外部网络出口被完全阻断 (403)"
    );
    expect(screen.queryByText(/"status": "pending"/)).not.toBeInTheDocument();
    expect(screen.queryByText("# PLAN")).not.toBeInTheDocument();
  });

  it("keeps the banner as progress only while interrupted", async () => {
    const user = setupUser();
    render(
      <CraftJobBannerView data={interruptedJob()} onCancel={jest.fn()} />
    );

    expect(screen.queryByTestId("craft-job-approve")).not.toBeInTheDocument();
    expect(screen.getByTestId("craft-job-cancel")).toBeInTheDocument();
    expect(screen.getByText("Waiting for a choice")).toBeInTheDocument();
    expect(screen.queryByTestId("craft-job-phases")).not.toBeInTheDocument();

    await user.click(screen.getByTestId("craft-job-banner"));
    expect(screen.getByTestId("craft-job-phases")).toBeInTheDocument();
  });

  it("shows a fallback when the error ends with a colon", async () => {
    const user = setupUser();
    render(
      <CraftJobBannerView
        data={{
          ...failedJob(),
          error_detail: "Phase gate retry limit reached:",
          specialists: [],
        }}
        onCancel={jest.fn()}
        onApprove={jest.fn()}
      />
    );

    await user.click(screen.getByTestId("craft-job-banner"));
    expect(screen.getByTestId("craft-job-error")).toHaveTextContent(
      "Phase gate retry limit reached"
    );
  });
});
