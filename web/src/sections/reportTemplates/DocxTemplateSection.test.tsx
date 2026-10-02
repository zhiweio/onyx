import { render, screen, setupUser } from "@tests/setup/test-utils";
import DocxTemplateSection from "@/sections/reportTemplates/DocxTemplateSection";
import type { DocxTemplateFields } from "@/sections/reportTemplates/DocxTemplateSection";

const mockToastError = jest.fn();

jest.mock("@opal/layouts", () => {
  const actual = jest.requireActual("@opal/layouts");
  return {
    ...actual,
    toast: {
      success: jest.fn(),
      error: (...args: unknown[]) => mockToastError(...args),
    },
  };
});

function template(
  overrides: Partial<DocxTemplateFields> = {}
): DocxTemplateFields {
  return {
    id: "tpl-1",
    slug: "initiation_report",
    body: "# Initiation",
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

  it("hides the contract badge and preview button on a legacy template", () => {
    render(
      <DocxTemplateSection
        template={template()}
        disabled={false}
        onUploaded={jest.fn()}
      />
    );

    expect(
      screen.queryByTestId("DocxTemplateSection/contract")
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Preview document" })
    ).not.toBeInTheDocument();
  });

  it("shows the contract badge, element count, and theme accent on a contract-style template", () => {
    render(
      <DocxTemplateSection
        template={template({
          contract: {
            required_elements: ["disclaimer", "sources"],
          },
          theme: { accent: "2E5E8C" },
        })}
        disabled={false}
        onUploaded={jest.fn()}
      />
    );

    expect(
      screen.getByTestId("DocxTemplateSection/contract")
    ).toBeInTheDocument();
    expect(screen.getByText("Contract")).toBeInTheDocument();
    expect(screen.getByText("2 required elements")).toBeInTheDocument();
    expect(screen.getByTestId("DocxTemplateSection/themeAccent")).toHaveStyle({
      backgroundColor: "#2E5E8C",
    });
    expect(
      screen.getByRole("button", { name: "Preview document" })
    ).toBeVisible();
  });

  it("previews a sample docx and lists the postcheck findings", async () => {
    const createObjectURL = jest.fn(() => "blob:mock");
    const revokeObjectURL = jest.fn();
    URL.createObjectURL = createObjectURL;
    URL.revokeObjectURL = revokeObjectURL;
    const anchorClick = jest
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => {});
    const user = setupUser();
    const preview = jest.fn().mockResolvedValue({
      docx_base64: btoa("fake-docx"),
      findings: [
        { check: "toc", passed: true, detail: "TOC field present" },
        { check: "disclaimer", passed: false, detail: "disclaimer missing" },
      ],
    });
    render(
      <DocxTemplateSection
        template={template({ contract: { require_toc: true } })}
        disabled={false}
        onUploaded={jest.fn()}
        preview={preview}
      />
    );

    await user.click(screen.getByRole("button", { name: "Preview document" }));

    expect(preview).toHaveBeenCalledWith(
      "# Initiation",
      { require_toc: true },
      undefined
    );
    expect(createObjectURL).toHaveBeenCalledWith(expect.any(Blob));
    expect(anchorClick).toHaveBeenCalledTimes(1);
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:mock");
    expect(screen.getByText("Quality checks")).toBeInTheDocument();
    expect(screen.getByText("toc")).toBeInTheDocument();
    expect(screen.getByText("TOC field present")).toBeInTheDocument();
    expect(screen.getByText("disclaimer missing")).toBeInTheDocument();
  });

  it("shows an error toast when the preview fails", async () => {
    URL.createObjectURL = jest.fn(() => "blob:mock");
    URL.revokeObjectURL = jest.fn();
    jest
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => {});
    const user = setupUser();
    const preview = jest.fn().mockRejectedValue(new Error("renderer down"));
    render(
      <DocxTemplateSection
        template={template({ contract: { require_toc: true } })}
        disabled={false}
        onUploaded={jest.fn()}
        preview={preview}
      />
    );

    await user.click(screen.getByRole("button", { name: "Preview document" }));

    expect(mockToastError).toHaveBeenCalledWith("renderer down");
    expect(screen.queryByText("Quality checks")).not.toBeInTheDocument();
  });
});
