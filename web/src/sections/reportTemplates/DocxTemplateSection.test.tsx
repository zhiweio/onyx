import { render, screen } from "@tests/setup/test-utils";
import DocxTemplateSection from "@/sections/reportTemplates/DocxTemplateSection";
import type { DocxTemplateFields } from "@/sections/reportTemplates/DocxTemplateSection";

function template(
  overrides: Partial<DocxTemplateFields> = {}
): DocxTemplateFields {
  return {
    id: "tpl-1",
    slug: "initiation_report",
    kind: "DOCX",
    asset_filename: "initiation_report.docx",
    ...overrides,
  };
}

describe("DocxTemplateSection", () => {
  it("shows the Word file without a schema or dropzone", () => {
    render(
      <DocxTemplateSection
        template={template()}
        disabled={false}
        onUploaded={jest.fn()}
      />
    );

    expect(screen.getByText("initiation_report.docx")).toBeInTheDocument();
    expect(screen.queryByText("{{entity_name}}")).not.toBeInTheDocument();
    expect(screen.queryByText("Browse files")).not.toBeInTheDocument();
    expect(screen.queryByText("Add property")).not.toBeInTheDocument();
    expect(screen.queryByText("Form")).not.toBeInTheDocument();
    expect(screen.queryByText("JSON")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Replace .docx" })).toBeVisible();
    expect(screen.getByTestId("DocxTemplateSection/input")).toBeInTheDocument();
  });
});
