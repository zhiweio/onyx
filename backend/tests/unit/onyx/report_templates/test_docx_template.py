import io
import zipfile

import pytest
from docx import Document

from onyx.error_handling.error_codes import OnyxErrorCode
from onyx.error_handling.exceptions import OnyxError
from onyx.report_templates.docx_template import validate_docx_asset
from onyx.system_catalog.builtin.word.generate import generate_official_docx


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
    asset_bytes = generate_official_docx("monthly_close")
    validate_docx_asset(asset_bytes)
    assert asset_bytes.startswith(b"PK")


def test_official_builder_uses_research_note_layout() -> None:
    asset_bytes = generate_official_docx("monthly_close")
    with zipfile.ZipFile(io.BytesIO(asset_bytes)) as archive:
        document_xml = archive.read("word/document.xml").decode("utf-8")
        styles_xml = archive.read("word/styles.xml").decode("utf-8")
        footer_xml = archive.read("word/footer1.xml").decode("utf-8")
        header_xml = archive.read("word/header1.xml").decode("utf-8")
    assert "微软雅黑" in styles_xml
    assert "黑体" in document_xml
    assert "宋体" not in styles_xml + document_xml
    assert "机密" not in footer_xml
    assert "PAGE" in footer_xml
    assert "{{company_header}}" in header_xml
    assert 'w:fill="185FA5"' in document_xml
    assert "{{entity_name}}" in document_xml
    assert "{{conclusion}}" in document_xml
