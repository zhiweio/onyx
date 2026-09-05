# PDF Reference

A PDF is a graph of objects, not a normal document tree. Text may draw in any order, and visual layout does not always match extraction order.

## Object Model Basics

- The catalog is the root object. It points to document-level structures.
- The pages tree lists page objects.
- Each page has resources such as fonts, images, color spaces, and form XObjects.
- Page content streams contain drawing commands for text, paths, and images.
- AcroForm data lives at the document level and references field widgets on pages.

## Text Extraction Failure Modes

Text extraction can fail or look strange for valid PDFs.

Common causes:

- Ligatures such as `fi` or `fl` are encoded as one glyph.
- Multi-column pages can extract in drawing order instead of reading order.
- Tables may flatten into irregular whitespace.
- Embedded fonts can use custom encodings that do not map cleanly to Unicode.
- Text can be stored as vector shapes or images, with no real text layer.

When extracted text is incomplete, report the limitation and use OCR or layout tools instead of guessing.

## AcroForm vs XFA

AcroForm is the classic PDF form model. `pypdf` can read and fill many AcroForm fields.

XFA forms store form data in XML packets. They are less portable and are not reliably filled by simple AcroForm tools. If a file uses XFA, say so and avoid claiming an AcroForm fill succeeded.

## Verifying Filled Forms

After writing a filled PDF, open it with `PdfReader` and call `get_fields()`. Compare each requested value with the field value that was written. Also inspect the file in a viewer when appearance matters, because some viewers show the visual appearance stream rather than the raw field value.

Set `NeedAppearances` when filling AcroForms so viewers know they should render field appearances from current values.
