import {
  htmlDownloadExtension,
  isHtmlFilePath,
} from "@/app/craft/utils/filePreviewPaths";

describe("isHtmlFilePath", () => {
  it("matches .html and .htm paths", () => {
    expect(isHtmlFilePath("outputs/君禾股份_财报解读_2026H1.html")).toBe(true);
    expect(isHtmlFilePath("outputs/report.HTML")).toBe(true);
    expect(isHtmlFilePath("outputs/page.htm")).toBe(true);
  });

  it("does not match other extensions", () => {
    expect(isHtmlFilePath("outputs/report.md")).toBe(false);
    expect(isHtmlFilePath("outputs/page.html.txt")).toBe(false);
  });
});

describe("htmlDownloadExtension", () => {
  it("returns the lowercase html extension", () => {
    expect(htmlDownloadExtension("outputs/Report.HTML")).toBe(".html");
    expect(htmlDownloadExtension("outputs/page.htm")).toBe(".htm");
  });
});
