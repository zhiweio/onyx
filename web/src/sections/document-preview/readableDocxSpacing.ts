const SINGLE_AUTO_LINE_TWIPS = "240";
const READABLE_LINE_TWIPS = "360";
const READABLE_CELL_PAD_TWIPS = "80";
const DOC_GRID_TAG = `<w:docGrid w:type="linesAndChars" w:linePitch="${READABLE_LINE_TWIPS}"/>`;
const READABLE_SPACING_TAG = `<w:spacing w:line="${READABLE_LINE_TWIPS}" w:lineRule="auto"/>`;
const PARAGRAPH_BLOCK =
  /<w:p\b(?![A-Za-z])[^>]*\/>|<w:p\b(?![A-Za-z])[\s\S]*?<\/w:p>/g;
const TABLE_CELL_BLOCK = /<w:tc\b(?![A-Za-z])[\s\S]*?<\/w:tc>/g;
const CELL_MARGIN_BLOCK =
  /<w:tblCellMar\b[\s\S]*?<\/w:tblCellMar>|<w:tcMar\b[\s\S]*?<\/w:tcMar>/g;

function isExactLineRule(tag: string): boolean {
  const rule = /\bw:lineRule="([^"]+)"/i.exec(tag)?.[1];
  return rule?.toLowerCase() === "exact";
}

function withReadableLineOnSpacingTag(tag: string): string {
  if (isExactLineRule(tag)) {
    return tag;
  }
  const line = /\bw:line="(\d+)"/i.exec(tag)?.[1];
  if (!line) {
    return tag.replace(
      /(\s*\/?>)/,
      ` w:line="${READABLE_LINE_TWIPS}" w:lineRule="auto"$1`
    );
  }
  if (line !== SINGLE_AUTO_LINE_TWIPS) {
    return tag;
  }
  return tag.replace(/\bw:line="240"/i, `w:line="${READABLE_LINE_TWIPS}"`);
}

function bumpSingleAutoLineSpacing(xml: string): string {
  return xml.replace(/<w:spacing\b[^>]*\/?>/gi, withReadableLineOnSpacingTag);
}

function ensureDocumentGrid(xml: string): string {
  if (!xml.includes("<w:sectPr")) {
    return xml;
  }
  const withOpenTags = xml.replace(
    /<w:sectPr\b[\s\S]*?<\/w:sectPr>/g,
    (sectPr) => {
      if (/<w:docGrid\b/i.test(sectPr)) {
        return sectPr;
      }
      return sectPr.replace(/<\/w:sectPr>/, `${DOC_GRID_TAG}</w:sectPr>`);
    }
  );
  return withOpenTags.replace(/<w:sectPr\b[^>]*\/>/g, (tag) => {
    if (/w:docGrid/i.test(tag)) {
      return tag;
    }
    return tag.replace(/\/>$/, `>${DOC_GRID_TAG}</w:sectPr>`);
  });
}

function insertReadableSpacingIntoPpr(pPr: string): string {
  if (/<w:pPr\b[^>]*\/>/i.test(pPr)) {
    return pPr.replace(/\/>$/, `>${READABLE_SPACING_TAG}</w:pPr>`);
  }
  if (/<w:spacing\b/i.test(pPr)) {
    return pPr.replace(/<w:spacing\b[^>]*\/?>/i, withReadableLineOnSpacingTag);
  }
  return pPr.replace(
    /<w:pPr\b[^>]*>/i,
    (open) => `${open}${READABLE_SPACING_TAG}`
  );
}

function ensureParagraphReadableLineSpacing(paragraphXml: string): string {
  if (/<w:p\b(?![A-Za-z])[^>]*\/>/i.test(paragraphXml)) {
    return paragraphXml.replace(
      /\/>$/,
      `><w:pPr>${READABLE_SPACING_TAG}</w:pPr></w:p>`
    );
  }
  if (/<w:pPr\b/i.test(paragraphXml)) {
    return paragraphXml.replace(
      /<w:pPr\b[\s\S]*?<\/w:pPr>|<w:pPr\b[^>]*\/>/i,
      insertReadableSpacingIntoPpr
    );
  }
  return paragraphXml.replace(
    /(<w:p\b(?![A-Za-z])[^>]*>)/i,
    `$1<w:pPr>${READABLE_SPACING_TAG}</w:pPr>`
  );
}

function ensureTableCellParagraphSpacing(xml: string): string {
  return xml.replace(TABLE_CELL_BLOCK, (cell) =>
    cell.replace(PARAGRAPH_BLOCK, ensureParagraphReadableLineSpacing)
  );
}

function bumpZeroTableCellVerticalMargins(xml: string): string {
  return xml.replace(CELL_MARGIN_BLOCK, (margins) =>
    margins.replace(/<w:(top|bottom)\b[^>]*\/?>/gi, (tag) => {
      const width = /\bw:w="(\d+)"/i.exec(tag)?.[1];
      if (width !== "0") {
        return tag;
      }
      return tag.replace(/\bw:w="0"/i, `w:w="${READABLE_CELL_PAD_TWIPS}"`);
    })
  );
}

export function rewriteDocxXmlForReadableLineSpacing(xml: string): string {
  return bumpZeroTableCellVerticalMargins(
    ensureTableCellParagraphSpacing(
      ensureDocumentGrid(bumpSingleAutoLineSpacing(xml))
    )
  );
}

export function isRewritableDocxPartName(name: string): boolean {
  return name.endsWith("styles.xml") || name.endsWith("document.xml");
}
