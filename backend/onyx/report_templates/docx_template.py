"""Word (.docx) report template assets.

A markdown body tells the agent which sections to write. An optional Word
file is a layout reference — letterhead, tables, styles — that the agent
follows when it writes the report.

The uploaded file is stored as-is. Tokens inside the document are not
extracted or stored; the agent reads the file itself.
"""

from __future__ import annotations

import io
import re
import zipfile
from typing import Final

# An uploaded .docx is untrusted input, so parse it with the hardened parser
# rather than stdlib ElementTree (billion-laughs / entity expansion).
from defusedxml.common import DefusedXmlException
from defusedxml.ElementTree import ParseError, fromstring

from onyx.error_handling.error_codes import OnyxErrorCode
from onyx.error_handling.exceptions import OnyxError

DOCX_CONTENT_TYPE: Final[str] = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)
# Templates are letterhead-and-tables documents, not media libraries.
MAX_ASSET_BYTES: Final[int] = 10 * 1024 * 1024

# Parts that can carry visible text. Word splits body, headers and footers into
# separate XML parts, and a template's letterhead usually lives in a header.
_TEXT_PART_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^word/(document|header\d*|footer\d*)\.xml$"
)


def _parse_word_part(part_xml: bytes) -> None:
    try:
        fromstring(part_xml)
    except DefusedXmlException as exc:
        # A declared entity or external reference — refuse the upload rather
        # than let it reach a parser that would expand it.
        raise OnyxError(
            OnyxErrorCode.INVALID_INPUT,
            "The Word template uses XML entities that are not allowed",
        ) from exc
    except ParseError as exc:
        raise OnyxError(
            OnyxErrorCode.INVALID_INPUT,
            "The Word template contains malformed XML",
        ) from exc


def validate_docx_asset(asset_bytes: bytes) -> None:
    """Reject files that are not a readable Word document.

    Raises ``OnyxError`` when the upload is not a valid .docx, so a
    mislabelled file fails at upload rather than at report time.
    """
    if len(asset_bytes) > MAX_ASSET_BYTES:
        raise OnyxError(
            OnyxErrorCode.PAYLOAD_TOO_LARGE,
            f"The Word template must be at most {MAX_ASSET_BYTES // (1024 * 1024)} MiB",
        )

    try:
        archive = zipfile.ZipFile(io.BytesIO(asset_bytes))
    except zipfile.BadZipFile as exc:
        raise OnyxError(
            OnyxErrorCode.INVALID_INPUT,
            "The file is not a valid .docx document",
        ) from exc

    with archive:
        names = set(archive.namelist())
        if "word/document.xml" not in names:
            raise OnyxError(
                OnyxErrorCode.INVALID_INPUT,
                "The file is not a Word document (no word/document.xml)",
            )
        for part in sorted(names):
            if _TEXT_PART_PATTERN.match(part):
                _parse_word_part(archive.read(part))


def sandbox_template_filename(slug: str) -> str:
    """The name the asset takes inside the sandbox template mount."""
    return f"{slug}.docx"
