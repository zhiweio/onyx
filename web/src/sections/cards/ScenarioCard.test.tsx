import { render, screen, setupUser } from "@tests/setup/test-utils";
import ScenarioCard from "@/sections/cards/ScenarioCard";
import type { Scenario } from "@/lib/scenarios/types";

function scenario(overrides: Partial<Scenario> = {}): Scenario {
  return {
    id: "pack-1",
    name: "Target landscape",
    description: "Map a target and competing trials.",
    author_user_id: "owner-id",
    public_permission: null,
    rules: { domain: "biomed" },
    report_template: "target_landscape",
    skill_ids: ["skill-a", "skill-b"],
    skills: [
      { skill_id: "skill-a", sort_order: 0 },
      { skill_id: "skill-b", sort_order: 1 },
    ],
    access_level: "OWNER",
    shared_user_ids: [],
    shared_group_ids: [],
    ...overrides,
  };
}

describe("ScenarioCard", () => {
  it("shows skill chips, domain, start run, and edit", () => {
    render(
      <ScenarioCard
        scenario={scenario()}
        skillNames={["biomed-literature", "biomed-clinical-intel"]}
        onEdit={jest.fn()}
      />
    );

    expect(screen.getAllByText("Target landscape").length).toBeGreaterThan(0);
    expect(screen.getByText("biomed-literature")).toBeInTheDocument();
    expect(screen.getByText("biomed-clinical-intel")).toBeInTheDocument();
    expect(screen.getByText("2 skills")).toBeInTheDocument();
    expect(screen.getByText("Biomedicine")).toBeInTheDocument();
    expect(screen.getByText("Personal")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Start run" })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Edit pack" })
    ).toBeInTheDocument();
  });

  it("shows a custom domain label as written", () => {
    render(
      <ScenarioCard
        scenario={scenario({
          rules: { domain: "新能源" },
        })}
        skillNames={["tax-compliance"]}
      />
    );

    expect(screen.getByText("新能源")).toBeInTheDocument();
  });

  it("lets viewers copy a workspace pack instead of editing it", () => {
    const onCustomize = jest.fn();
    render(
      <ScenarioCard
        scenario={scenario({
          author_user_id: null,
          access_level: "VIEWER",
          public_permission: "VIEWER",
        })}
        skillNames={["biomed-literature", "biomed-clinical-intel"]}
        onEdit={jest.fn()}
        onCustomize={onCustomize}
      />
    );

    expect(screen.getByText("Workspace")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Edit pack" })
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Save as my pack" })
    ).toBeInTheDocument();
  });

  it("starts a run without opening the pack", async () => {
    const user = setupUser();
    const onClick = jest.fn();
    const onStart = jest.fn();
    render(
      <ScenarioCard
        scenario={scenario()}
        skillNames={["biomed-literature", "biomed-clinical-intel"]}
        onClick={onClick}
        onStart={onStart}
      />
    );

    await user.click(screen.getByRole("button", { name: "Start run" }));

    expect(onStart).toHaveBeenCalledTimes(1);
    expect(onClick).not.toHaveBeenCalled();
  });

  it("opens share and delete without starting a run", async () => {
    const user = setupUser();
    const onShare = jest.fn();
    const onDelete = jest.fn();
    const onStart = jest.fn();
    render(
      <ScenarioCard
        scenario={scenario()}
        skillNames={["biomed-literature", "biomed-clinical-intel"]}
        onShare={onShare}
        onDelete={onDelete}
        onStart={onStart}
      />
    );

    await user.click(screen.getByRole("button", { name: "Share pack" }));
    await user.click(
      screen.getByRole("button", { name: 'Delete "Target landscape"?' })
    );

    expect(onShare).toHaveBeenCalledTimes(1);
    expect(onDelete).toHaveBeenCalledTimes(1);
    expect(onStart).not.toHaveBeenCalled();
  });
});
