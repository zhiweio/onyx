import {
  filePreviewKind,
  isChatProjectFileDocumentId,
  isDocumentPreviewKind,
  isEditableDocumentKind,
  resolveDocumentPreviewMode,
} from "@/sections/document-preview/filePreviewKind";

describe("filePreviewKind", () => {
  it("classifies office and pdf files as document kinds", () => {
    expect(filePreviewKind("report.docx")).toBe("docx");
    expect(filePreviewKind("legacy.doc")).toBe("doc");
    expect(filePreviewKind("rates.xlsx")).toBe("xlsx");
    expect(filePreviewKind("deck.pptx")).toBe("pptx");
    expect(filePreviewKind("notes.csv")).toBe("csv");
    expect(filePreviewKind("file.bin", "application/pdf")).toBe("pdf");
  });

  it("does not treat compound extensions as office files", () => {
    expect(filePreviewKind("notes.ppt.txt")).toBe("text");
    expect(filePreviewKind("backup.docx.txt")).toBe("text");
  });

  it("marks pdf, word, and spreadsheet as editable", () => {
    expect(isEditableDocumentKind("pdf")).toBe(true);
    expect(isEditableDocumentKind("docx")).toBe(true);
    expect(isEditableDocumentKind("xlsx")).toBe(true);
    expect(isEditableDocumentKind("pptx")).toBe(false);
    expect(isEditableDocumentKind("doc")).toBe(false);
  });

  it("treats office kinds as document previews", () => {
    expect(isDocumentPreviewKind("docx")).toBe(true);
    expect(isDocumentPreviewKind("markdown")).toBe(false);
  });

  it("opens project pdf, word, and excel in edit mode", () => {
    for (const surface of ["craft-project", "chat-project"] as const) {
      expect(resolveDocumentPreviewMode(surface, "pdf")).toBe("edit");
      expect(resolveDocumentPreviewMode(surface, "docx")).toBe("edit");
      expect(resolveDocumentPreviewMode(surface, "xlsx")).toBe("edit");
      expect(resolveDocumentPreviewMode(surface, "pptx")).toBe("view");
    }
  });

  it("keeps sandbox, library, and chat preview in view mode", () => {
    for (const surface of ["sandbox", "library", "chat-preview"] as const) {
      expect(resolveDocumentPreviewMode(surface, "pdf")).toBe("view");
      expect(resolveDocumentPreviewMode(surface, "docx")).toBe("view");
      expect(resolveDocumentPreviewMode(surface, "xlsx")).toBe("view");
    }
  });

  it("detects chat project file document ids", () => {
    expect(isChatProjectFileDocumentId("project_file__abc")).toBe(true);
    expect(isChatProjectFileDocumentId("FILE_CONNECTOR__abc")).toBe(false);
  });
});
