"""Shared Markdown parse for Craft document export.

Word and PDF both start from one GFM AST (mistune + table / strikethrough /
url / footnotes). HTML is the print interchange used by the PDF renderer and
by a future WeasyPrint or Chromium print path.
"""

from __future__ import annotations

from typing import Any

import mistune

MISTUNE_PLUGINS = ("table", "strikethrough", "url", "footnotes")

# XML 1.0 forbids C0 controls except tab/newline/CR, UTF-16 surrogates, and
# U+FFFE/U+FFFF. Mapped to None for str.translate.
_XML_INVALID_TRANSLATION = {
    **{code: None for code in range(0x20) if code not in (0x09, 0x0A, 0x0D)},
    **{code: None for code in range(0xD800, 0xE000)},
    0xFFFE: None,
    0xFFFF: None,
}

_PRINT_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<title>Document</title>
<style>
  @page { size: letter; margin: 1in; }
  body {
    font-family: "Songti SC", "SimSun", "STSong", serif;
    font-size: 12pt;
    line-height: 1.45;
    color: #222;
  }
  h1, h2, h3, h4, h5, h6 {
    color: #0F4761;
    font-family: "Heiti SC", "SimHei", "STHeiti", sans-serif;
    font-weight: normal;
  }
  h1 { font-size: 20pt; }
  h2 { font-size: 16pt; }
  h3 { font-size: 14pt; }
  pre, code { font-family: "Courier New", Courier, monospace; }
  pre { background: #F4F4F4; padding: 8px; }
  blockquote {
    margin-left: 0.33in;
    margin-right: 0.33in;
    color: #444;
  }
  table { border-collapse: collapse; }
  th, td { border: 0.25pt solid #CCC; padding: 4px 6px; }
  th { font-weight: bold; }
  a { color: #4F81BD; text-decoration: none; }
</style>
</head>
<body>
__BODY__
</body>
</html>
"""

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
    return _PRINT_HTML.replace("__BODY__", str(body))
