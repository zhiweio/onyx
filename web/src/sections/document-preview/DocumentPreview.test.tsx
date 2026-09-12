import type { ReactNode } from "react";
import { render, screen } from "@tests/setup/test-utils";
import DocumentPreview from "@/sections/document-preview/DocumentPreview";

jest.mock("next/dynamic", () => () => {
  function MockHost({
    mode,
    toolbarActions,
  }: {
    mode?: string;
    toolbarActions?: ReactNode;
  }) {
    return (
      <div>
        <div>{`document-host-${mode ?? "view"}`}</div>
        {toolbarActions}
      </div>
    );
  }
  return MockHost;
});

describe("DocumentPreview", () => {
  it("opens a project Word file in edit mode", () => {
    render(
      <DocumentPreview
        src="/api/craft-projects/1/files/2"
        fileName="报告.docx"
        mode="edit"
        onSaveBytes={async () => undefined}
      />
    );

    expect(screen.getByText("document-host-edit")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save" })).toBeInTheDocument();
  });

  it("keeps sandbox and chat preview Word files in view mode", () => {
    render(
      <DocumentPreview
        src="/api/build/sessions/1/files/report.docx"
        fileName="报告.docx"
        mode="view"
      />
    );

    expect(screen.getByText("document-host-view")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Save" })
    ).not.toBeInTheDocument();
  });
});
