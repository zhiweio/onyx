"""Word (.docx) report template assets.

A markdown template tells the agent what sections to write. A Word template
additionally fixes the *formatting* — letterhead, tables, styles — which is what
finance and regulatory reporting usually requires.

The contract between the template and the agent is the placeholder set. Tokens
are written ``{{name}}`` in the document, extracted here at upload time, stored
alongside the asset, and handed to the agent in SCENARIO.md. The agent fills
them with the ``docx`` skill's ``fill_template.py``, which understands tokens
split across runs — the usual way Word fragments text.
"""

from __future__ import annotations

import io
import re
import zipfile
from typing import Final
from xml.etree.ElementTree import Element

# An uploaded .docx is untrusted input, so parse it with the hardened parser
# rather than stdlib ElementTree (billion-laughs / entity expansion).
from defusedxml.common import DefusedXmlException
from defusedxml.ElementTree import ParseError, fromstring

from onyx.error_handling.error_codes import OnyxErrorCode
from onyx.error_handling.exceptions import OnyxError
from onyx.report_templates.placeholders import (
    PlaceholderSpec,
    merge_placeholder_schema,
)

DOCX_CONTENT_TYPE: Final[str] = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)
# Templates are letterhead-and-tables documents, not media libraries.
MAX_ASSET_BYTES: Final[int] = 10 * 1024 * 1024
MAX_PLACEHOLDERS: Final[int] = 200
PLACEHOLDER_MAX_LENGTH: Final[int] = 64

_WORD_NAMESPACE: Final[str] = (
    "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
)
_PARAGRAPH_TAG: Final[str] = f"{{{_WORD_NAMESPACE}}}p"
_TEXT_TAG: Final[str] = f"{{{_WORD_NAMESPACE}}}t"

# Parts that can carry visible text. Word splits body, headers and footers into
# separate XML parts, and a template's letterhead usually lives in a header.
_TEXT_PART_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^word/(document|header\d*|footer\d*)\.xml$"
)
_PLACEHOLDER_PATTERN: Final[re.Pattern[str]] = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")
# Mirrors what fill_template.py can address and what a person can read.
_PLACEHOLDER_NAME_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^[A-Za-z0-9_][A-Za-z0-9_.-]*$"
)


def _paragraph_texts(part_xml: bytes) -> list[str]:
    """Return one joined string per paragraph.

    Joining at paragraph level is what makes split tokens visible: Word
    routinely fragments ``{{total}}`` into ``{{to`` + ``tal}}`` across runs when
    formatting or spellcheck state changes mid-token.
    """
    try:
        root: Element = fromstring(part_xml)
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
    return [
        "".join(node.text or "" for node in paragraph.iter(_TEXT_TAG))
        for paragraph in root.iter(_PARAGRAPH_TAG)
    ]


def extract_docx_placeholders(asset_bytes: bytes) -> list[str]:
    """Validate a .docx and return its ``{{placeholder}}`` names, deduplicated.

    Raises ``OnyxError`` when the upload is not a readable Word document, so a
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

        found: set[str] = set()
        for part in sorted(names):
            if not _TEXT_PART_PATTERN.match(part):
                continue
            for paragraph in _paragraph_texts(archive.read(part)):
                found.update(_PLACEHOLDER_PATTERN.findall(paragraph))

    return _normalize_placeholder_names(found)


def extract_docx_placeholder_schema(
    asset_bytes: bytes,
    overlay: list[PlaceholderSpec] | None = None,
) -> list[PlaceholderSpec]:
    """Names from the file, metadata from ``overlay`` when present."""
    return merge_placeholder_schema(extract_docx_placeholders(asset_bytes), overlay)


def _normalize_placeholder_names(raw: set[str]) -> list[str]:
    normalized: set[str] = set()
    for candidate in raw:
        name = candidate.strip()
        if not name:
            continue
        if len(name) > PLACEHOLDER_MAX_LENGTH:
            raise OnyxError(
                OnyxErrorCode.INVALID_INPUT,
                f"Placeholder '{name[:32]}…' is longer than "
                f"{PLACEHOLDER_MAX_LENGTH} characters",
            )
        if not _PLACEHOLDER_NAME_PATTERN.fullmatch(name):
            raise OnyxError(
                OnyxErrorCode.INVALID_INPUT,
                f"Placeholder '{name}' must use letters, numbers, '_', '-' or '.'",
            )
        normalized.add(name)

    if len(normalized) > MAX_PLACEHOLDERS:
        raise OnyxError(
            OnyxErrorCode.INVALID_INPUT,
            f"The template declares more than {MAX_PLACEHOLDERS} placeholders",
        )
    return sorted(normalized)


def sandbox_template_filename(slug: str) -> str:
    """The name the asset takes inside the sandbox template mount."""
    return f"{slug}.docx"
