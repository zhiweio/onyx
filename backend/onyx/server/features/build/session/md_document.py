"""Shared Markdown parse for Craft document export.

Word and PDF both start from one GFM AST (mistune + table / strikethrough /
url / footnotes). HTML is the print interchange used by the PDF renderer and
by a future WeasyPrint or Chromium print path.
"""

from __future__ import annotations

from typing import Any

import mistune

from onyx.server.features.build.session.md_export_style import print_html_document

MISTUNE_PLUGINS = ("table", "strikethrough", "url", "footnotes")

# XML 1.0 forbids C0 controls except tab/newline/CR, UTF-16 surrogates, and
# U+FFFE/U+FFFF. Mapped to None for str.translate.
_XML_INVALID_TRANSLATION = {
    **{code: None for code in range(0x20) if code not in (0x09, 0x0A, 0x0D)},
    **{code: None for code in range(0xD800, 0xE000)},
    0xFFFE: None,
    0xFFFF: None,
}

Node = dict[str, Any]

_ast_parser = mistune.create_markdown(renderer=None, plugins=list(MISTUNE_PLUGINS))
_html_parser = mistune.create_markdown(renderer="html", plugins=list(MISTUNE_PLUGINS))


def strip_invalid_xml_chars(text: str) -> str:
    """Drop characters XML 1.0 forbids (NULL and most C0 controls)."""
    return text.translate(_XML_INVALID_TRANSLATION)


def parse_markdown(md_text: str) -> list[Node]:
    """Parse GFM Markdown into a mistune AST."""
    tokens = _ast_parser(strip_invalid_xml_chars(md_text))
    return tokens if isinstance(tokens, list) else []


def markdown_to_html(md_text: str) -> str:
    """Render GFM Markdown to a print-ready HTML document."""
    body = _html_parser(strip_invalid_xml_chars(md_text))
    return print_html_document(str(body))
