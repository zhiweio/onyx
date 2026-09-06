# DOCX Reference

A `.docx` file is a ZIP package. Most document content lives under `word/`. You can unpack it with any ZIP tool when `python-docx` does not expose the part you need.

## Package Layout

Common files:

- `[Content_Types].xml` declares the content type for each part.
- `_rels/.rels` points to the main Office document part.
- `word/document.xml` stores the body: paragraphs, tables, runs, fields, bookmarks, comments anchors, and tracked changes.
- `word/styles.xml` stores paragraph, character, table, and numbering styles.
- `word/numbering.xml` stores list definitions and concrete list instances.
- `word/comments.xml` stores comment bodies and metadata.
- `word/_rels/document.xml.rels` maps relationship ids to images, hyperlinks, headers, footers, and other parts.

## How python-docx Maps to OOXML

`Document` wraps `word/document.xml`. Paragraphs map to `w:p` elements. Runs map to `w:r` elements. Text usually lives in `w:t`. Tables map to `w:tbl`, rows to `w:tr`, and cells to `w:tc`.

Styles are referenced by id from document content. Setting `paragraph.style = "Heading 1"` writes a style reference; the style definition remains in `styles.xml`. Direct run formatting writes properties on the run itself.

## Comments and Review Markup

Comment text is in `word/comments.xml`. The body contains anchors such as `w:commentRangeStart`, `w:commentRangeEnd`, and `w:commentReference`. Tracked insertions are `w:ins`; tracked deletions are `w:del`. Deleted text often uses `w:delText` instead of `w:t`.

`python-docx` is best for stable document creation and light editing. Use XML parsing for review data, unusual fields, or features not mapped by the library.

## Common Pitfalls

### Placeholder Text Split Across Runs

Word can split a visible token across runs because of spelling markers, revisions, formatting changes, or internal editing history. A search of each run can miss `{{client_name}}`. Build the full paragraph text, locate the token, then map character positions back to runs.

### Style Inheritance

A run can look bold because the paragraph style, character style, or theme makes it bold. `run.bold` may be `None`, not `False`. Treat `None` as inherited formatting.

### List Numbering

List appearance comes from `styles.xml` and `numbering.xml`. Copying a paragraph without the related numbering definition can break bullets or numbering. When making complex list edits, prefer using existing styled list paragraphs in the template.

### Paragraph Text Assignment

Assigning `paragraph.text` removes the existing runs. This can erase formatting, fields, hyperlinks, bookmarks, and revision anchors. Use run-level edits when the original structure matters.
