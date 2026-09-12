import {
  BINARY_DOCUMENT_TEXT_ERROR,
  isBinaryDocument,
} from "@/sections/document-preview/binaryGuard";

describe("isBinaryDocument", () => {
  it("detects PDF and ZIP magic bytes", () => {
    expect(
      isBinaryDocument(new Uint8Array([0x25, 0x50, 0x44, 0x46]), "x.bin")
    ).toBe(true);
    expect(
      isBinaryDocument(new Uint8Array([0x50, 0x4b, 0x03, 0x04]), "x.bin")
    ).toBe(true);
    expect(
      isBinaryDocument(new TextEncoder().encode("# title"), "notes.md")
    ).toBe(false);
  });

  it("detects office extensions even without magic", () => {
    expect(isBinaryDocument(new Uint8Array([0x00]), "report.docx")).toBe(true);
    expect(isBinaryDocument(new Uint8Array([0x00]), "notes.ppt.txt")).toBe(
      false
    );
  });

  it("exposes a stable text-fallback error", () => {
    expect(BINARY_DOCUMENT_TEXT_ERROR.length).toBeGreaterThan(0);
  });
});
