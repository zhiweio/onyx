import { render, screen, setupUser, waitFor } from "@tests/setup/test-utils";
import { adminCatalogDetailKey } from "@/lib/system-catalog/api";
import type {
  SystemReportTemplateItem,
  SystemSkillItem,
} from "@/lib/system-catalog/types";
import EditCatalogModal from "@/views/admin/CraftCatalogPage/EditCatalogModal";

function skillItem(
  overrides: Partial<SystemSkillItem> = {}
): SystemSkillItem {
  return {
    id: "skill-1",
    slug: "chart",
    name: "Chart generation",
    description: "Generate charts from JSON.",
    category: "GRAPHIC",
    tags: ["chart", "graphic"],
    publish_status: "PUBLISHED",
    version: 2,
    changelog: "",
    origin: "BUILTIN",
    published_at: "2026-09-01T00:00:00Z",
    created_at: "2026-09-01T00:00:00Z",
    updated_at: "2026-09-01T00:00:00Z",
    is_built_in_content: true,
    instructions_markdown: null,
    ...overrides,
  };
}

function templateItem(): SystemReportTemplateItem {
  return {
    id: "template-1",
    slug: "audit_note",
    name: "Audit note",
    description: "A short audit note.",
    category: "REPORT",
    tags: ["audit"],
    publish_status: "DRAFT",
    version: 0,
    changelog: "",
    origin: "ADMIN",
    published_at: null,
    created_at: "2026-09-01T00:00:00Z",
    updated_at: "2026-09-01T00:00:00Z",
    body: "# Audit\n\nWrite the finding.",
    kind: "MARKDOWN",
    asset_filename: null,
  };
}

describe("EditCatalogModal", () => {
  it("edits catalog listing metadata instead of opening the skill editor", async () => {
    const onSave = jest.fn().mockResolvedValue(undefined);
    const item = skillItem();

    render(
      <EditCatalogModal
        kind="skills"
        item={item}
        pending={false}
        onClose={jest.fn()}
        onSave={onSave}
      />,
      {
        swrConfig: {
          fallback: {
            [adminCatalogDetailKey("skills", item.id)]: {
              ...item,
              instructions_markdown:
                "# Chart skill\n\nDraw a chart from JSON.",
            },
          },
        },
      }
    );

    expect(screen.getByText('Edit "Chart generation"')).toBeInTheDocument();
    expect(document.getElementById("catalog-listing-slug")).toHaveValue(
      "chart"
    );
    expect(screen.getByText("Built-in skill")).toBeInTheDocument();
    expect(screen.getByRole("combobox")).toBeInTheDocument();
    expect(document.body.innerHTML).not.toContain("/craft/v1/skills/new");

    const description = document.getElementById(
      "catalog-listing-description"
    ) as HTMLTextAreaElement;
    expect(description.closest(".w-full.min-w-0")).not.toBeNull();

    await waitFor(() => {
      expect(screen.getByText("Draw a chart from JSON.")).toBeInTheDocument();
    });

    const user = setupUser();
    await user.clear(description);
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();

    await user.type(description, "  Updated gallery copy.  ");
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
    expect(onSave).toHaveBeenCalledWith({
      name: "Chart generation",
      description: "Updated gallery copy.",
      category: "GRAPHIC",
      tags: ["chart", "graphic"],
    });
  });

  it("keeps report template body on the listing form", () => {
    render(
      <EditCatalogModal
        kind="report-templates"
        item={templateItem()}
        pending={false}
        onClose={jest.fn()}
        onSave={jest.fn()}
      />
    );

    expect(document.getElementById("catalog-listing-body")).toHaveValue(
      "# Audit\n\nWrite the finding."
    );
    expect(screen.queryByText("Skill contents")).not.toBeInTheDocument();
    expect(screen.queryByText("Built-in skill")).not.toBeInTheDocument();
  });
});
