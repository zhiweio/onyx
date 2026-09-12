import { useState } from "react";
import { render, screen, setupUser, within } from "@tests/setup/test-utils";
import ScenarioComposer from "@/sections/scenarios/editor/ScenarioComposer";

jest.mock("next/navigation", () => ({
  useRouter: () => ({
    push: jest.fn(),
    replace: jest.fn(),
    back: jest.fn(),
  }),
}));
import { emptyPlaybookDraft } from "@/lib/scenarios/types";
import type {
  ConditionalDraft,
  ScenarioDraft,
  ScenarioEditorMode,
} from "@/sections/scenarios/editor/types";

const SKILLS = [
  { key: "skill-a", name: "Alpha skill", description: "First skill" },
  { key: "skill-b", name: "Beta skill", description: "Second skill" },
];

function emptyDraft(overrides: Partial<ScenarioDraft> = {}): ScenarioDraft {
  return {
    name: "",
    description: "",
    skillKeys: [],
    reportTemplate: "",
    domain: "custom",
    playbook: emptyPlaybookDraft(),
    extras: {},
    slug: "",
    category: "GENERAL",
    tags: [],
    ...overrides,
  };
}

function ComposerHarness({
  mode = "user",
}: {
  mode?: ScenarioEditorMode;
}) {
  const [draft, setDraft] = useState<ScenarioDraft>(emptyDraft);
  const [conditionals, setConditionals] = useState<ConditionalDraft[]>([]);
  const canSave =
    draft.name.trim().length > 0 &&
    draft.skillKeys.length >= 1 &&
    (mode !== "catalog" || draft.slug.trim().length > 0);

  return (
    <ScenarioComposer
      mode={mode}
      isCreating
      isLoading={false}
      error={undefined}
      canEdit
      fieldsLocked={false}
      draft={draft}
      conditionals={conditionals}
      onDraftChange={(patch) => setDraft((current) => ({ ...current, ...patch }))}
      onConditionalsChange={setConditionals}
      skillCatalog={SKILLS}
      templates={[{ slug: "rpt", name: "Audit report" }]}
      isDirty={
        draft.name.length > 0 ||
        draft.skillKeys.length > 0 ||
        draft.playbook.objective.length > 0
      }
      onCancel={() => undefined}
      onSave={() => undefined}
      saving={false}
      canSave={canSave}
    />
  );
}

async function addSkillByName(
  user: ReturnType<typeof setupUser>,
  name: string
) {
  if (!screen.queryByPlaceholderText("Search skills...")) {
    await user.click(screen.getByRole("button", { name: "Add skill" }));
    await screen.findByPlaceholderText("Search skills...");
  }
  const key = SKILLS.find((skill) => skill.name === name)?.key;
  if (!key) {
    throw new Error(`Unknown catalog skill ${name}`);
  }
  const row = await screen.findByTestId(`SkillPipeline/catalog-${key}`);
  await user.click(within(row).getByRole("button", { name: "Add skill" }));
}

describe("ScenarioComposer", () => {
  jest.setTimeout(15000);

  beforeEach(() => {
    window.HTMLElement.prototype.scrollIntoView = jest.fn();
  });

  it("keeps Save disabled until name and a skill are set", async () => {
    const user = setupUser();
    render(<ComposerHarness />);

    const save = screen.getByTestId("ScenarioComposer/save");
    expect(save).toBeDisabled();

    await user.type(screen.getByPlaceholderText("Scenario name"), "Due diligence");
    expect(save).toBeDisabled();

    await addSkillByName(user, "Alpha skill");

    expect(save).toBeEnabled();
    expect(screen.getByText("Unsaved")).toBeInTheDocument();
  });

  it("adds skills, reorders them, and mirrors playbook edits in the preview", async () => {
    const user = setupUser();
    render(<ComposerHarness />);

    await addSkillByName(user, "Alpha skill");
    await addSkillByName(user, "Beta skill");
    await user.keyboard("{Escape}");

    const firstRow = screen.getByTestId("SkillPipeline/row-skill-a");
    const secondRow = screen.getByTestId("SkillPipeline/row-skill-b");
    expect(
      firstRow.compareDocumentPosition(secondRow) & Node.DOCUMENT_POSITION_FOLLOWING
    ).toBeTruthy();

    const handle = within(firstRow).getByRole("button", {
      name: "Drag to reorder",
    });
    handle.focus();
    await user.keyboard("{ArrowDown}");

    const afterFirst = screen.getByTestId("SkillPipeline/row-skill-b");
    const afterSecond = screen.getByTestId("SkillPipeline/row-skill-a");
    expect(
      afterFirst.compareDocumentPosition(afterSecond) &
        Node.DOCUMENT_POSITION_FOLLOWING
    ).toBeTruthy();

    await user.type(
      screen.getByPlaceholderText("What a successful run produces"),
      "Confirm the legal entity."
    );

    await user.click(screen.getByText("What the agent reads"));

    const preview = await screen.findByTestId("ScenarioComposer/preview");
    expect(preview).toHaveTextContent(
      "Use only these skills unless the user asks otherwise:"
    );
    expect(preview).toHaveTextContent("## Domain");
    expect(preview).toHaveTextContent("## Objective");
    expect(preview).toHaveTextContent("Confirm the legal entity.");
    expect(preview).toHaveTextContent("Beta skill");
    expect(preview).toHaveTextContent("Alpha skill");
    expect(screen.getByText("Unsaved")).toBeInTheDocument();
  });

  it("requires a slug when creating a catalog scenario", async () => {
    const user = setupUser();
    render(<ComposerHarness mode="catalog" />);

    await user.type(screen.getByPlaceholderText("Scenario name"), "KYB pack");
    await addSkillByName(user, "Alpha skill");

    const save = screen.getByTestId("ScenarioComposer/save");
    expect(save).toBeDisabled();

    await user.type(screen.getByPlaceholderText("unique-slug"), "kyb-pack");
    expect(save).toBeEnabled();
  });
});
