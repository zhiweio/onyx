import { rewriteDocxXmlForReadableLineSpacing } from "@/sections/document-preview/readableDocxSpacing";

describe("rewriteDocxXmlForReadableLineSpacing", () => {
  it("raises single auto spacing to 1.5 and adds a CJK document grid", () => {
    const xml = [
      '<w:style w:styleId="Normal">',
      '<w:pPr><w:spacing w:line="240" w:lineRule="auto"/></w:pPr>',
      "</w:style>",
      '<w:sectPr><w:pgSz w:w="12240" w:h="15840"/></w:sectPr>',
    ].join("");

    const rewritten = rewriteDocxXmlForReadableLineSpacing(xml);

    expect(rewritten).toContain('w:line="360"');
    expect(rewritten).not.toContain('w:line="240"');
    expect(rewritten).toContain(
      '<w:docGrid w:type="linesAndChars" w:linePitch="360"/>'
    );
  });

  it("does not change exact line spacing or an existing document grid", () => {
    const xml = [
      '<w:spacing w:line="240" w:lineRule="exact"/>',
      "<w:sectPr>",
      '<w:docGrid w:type="lines" w:linePitch="312"/>',
      "</w:sectPr>",
    ].join("");

    expect(rewriteDocxXmlForReadableLineSpacing(xml)).toBe(xml);
  });

  it("writes 1.5 line spacing onto table cell paragraphs that have none", () => {
    const xml = [
      "<w:tc>",
      '<w:p><w:pPr><w:pStyle w:val="Compact"/></w:pPr>',
      "<w:r><w:t>中文风险说明</w:t></w:r>",
      "</w:p>",
      "</w:tc>",
    ].join("");

    const rewritten = rewriteDocxXmlForReadableLineSpacing(xml);

    expect(rewritten).toContain('w:line="360"');
    expect(rewritten).toContain('w:lineRule="auto"');
    expect(rewritten).toContain('w:pStyle w:val="Compact"');
  });

  it("adds readable spacing to empty self-closing table cell paragraphs", () => {
    const rewritten = rewriteDocxXmlForReadableLineSpacing(
      "<w:tc><w:p/></w:tc>"
    );

    expect(rewritten).toContain(
      '<w:p><w:pPr><w:spacing w:line="360" w:lineRule="auto"/></w:pPr></w:p>'
    );
  });

  it("adds line spacing when a cell paragraph only has before/after spacing", () => {
    const xml = [
      "<w:tc>",
      '<w:p><w:pPr><w:spacing w:before="36" w:after="36"/></w:pPr>',
      "<w:r><w:t>单元格</w:t></w:r>",
      "</w:p>",
      "</w:tc>",
    ].join("");

    const rewritten = rewriteDocxXmlForReadableLineSpacing(xml);

    expect(rewritten).toContain('w:before="36"');
    expect(rewritten).toContain('w:after="36"');
    expect(rewritten).toContain('w:line="360"');
    expect(rewritten).toContain('w:lineRule="auto"');
  });

  it("gives table cells vertical padding when Word left top and bottom at 0", () => {
    const xml = [
      "<w:tblCellMar>",
      '<w:top w:w="0" w:type="dxa"/>',
      '<w:left w:w="108" w:type="dxa"/>',
      '<w:bottom w:w="0" w:type="dxa"/>',
      '<w:right w:w="108" w:type="dxa"/>',
      "</w:tblCellMar>",
    ].join("");

    const rewritten = rewriteDocxXmlForReadableLineSpacing(xml);

    expect(rewritten).toContain('<w:top w:w="80" w:type="dxa"/>');
    expect(rewritten).toContain('<w:bottom w:w="80" w:type="dxa"/>');
    expect(rewritten).toContain('<w:left w:w="108" w:type="dxa"/>');
  });
});
