import { render, screen, setupUser } from "@tests/setup/test-utils";
import ReportTemplateCard from "@/sections/cards/ReportTemplateCard";
import type { ReportTemplate } from "@/lib/report-templates/types";

function template(overrides: Partial<ReportTemplate> = {}): ReportTemplate {
  return {
    id: "tpl-1",
    slug: "compliance_risk",
    name: "合规风险预警",
    description: "Tax compliance risk brief for an entity.",
    body: "# 合规风险预警报告",
    author_user_id: null,
    is_builtin: true,
    referenced_count: 2,
    can_edit: true,
    can_delete: false,
    created_at: "2026-08-01T00:00:00Z",
    updated_at: "2026-08-01T00:00:00Z",
    ...overrides,
  };
}

describe("ReportTemplateCard", () => {
  it("shows name, slug, workspace origin, and pack count", () => {
    render(<ReportTemplateCard template={template()} />);

    expect(screen.getAllByText("合规风险预警").length).toBeGreaterThan(0);
    expect(screen.getByText("compliance_risk")).toBeInTheDocument();
    expect(screen.getByText("Workspace")).toBeInTheDocument();
    expect(screen.getByText("2 packs")).toBeInTheDocument();
  });

  it("blocks delete when packs still use the template", () => {
    render(<ReportTemplateCard template={template()} onDelete={jest.fn()} />);

    expect(
      screen.getByRole("button", {
        name: "Cannot delete: packs use this template",
      })
    ).toBeDisabled();
  });

  it("lets the owner delete an unused personal template", async () => {
    const user = setupUser();
    const onDelete = jest.fn();
    const onClick = jest.fn();
    render(
      <ReportTemplateCard
        template={template({
          author_user_id: "owner-id",
          is_builtin: false,
          referenced_count: 0,
          can_delete: true,
        })}
        onClick={onClick}
        onDelete={onDelete}
      />
    );

    await user.click(screen.getByRole("button", { name: "Delete template" }));

    expect(onDelete).toHaveBeenCalledTimes(1);
    expect(onClick).not.toHaveBeenCalled();
  });
});
