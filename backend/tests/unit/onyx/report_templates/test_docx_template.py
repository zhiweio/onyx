import io
import zipfile

import pytest
from docx import Document

from onyx.error_handling.error_codes import OnyxErrorCode
from onyx.error_handling.exceptions import OnyxError
from onyx.report_templates.docx_template import validate_docx_asset


def _minimal_docx() -> bytes:
    import io

    from docx import Document

    document = Document()
    document.add_heading("Outline", level=1)
    document.add_paragraph("Body")
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _docx_bytes() -> bytes:
    document = Document()
    document.add_paragraph("Layout reference.")
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def test_validate_accepts_a_readable_docx() -> None:
    validate_docx_asset(_docx_bytes())


def test_validate_rejects_a_file_that_is_not_a_docx() -> None:
    with pytest.raises(OnyxError) as caught:
        validate_docx_asset(b"definitely not a zip")
    assert caught.value.error_code is OnyxErrorCode.INVALID_INPUT


def test_validate_rejects_a_zip_without_a_word_document() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("notes.txt", "hello")
    with pytest.raises(OnyxError) as caught:
        validate_docx_asset(buffer.getvalue())
    assert caught.value.error_code is OnyxErrorCode.INVALID_INPUT


def test_official_builder_returns_a_readable_docx() -> None:
    asset_bytes = _minimal_docx()
    validate_docx_asset(asset_bytes)
    assert asset_bytes.startswith(b"PK")
