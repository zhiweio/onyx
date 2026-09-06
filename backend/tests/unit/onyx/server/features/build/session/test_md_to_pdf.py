from onyx.server.features.build.session.md_to_pdf import markdown_to_pdf_bytes


def test_markdown_to_pdf_bytes_writes_pdf_header() -> None:
    pdf = markdown_to_pdf_bytes("# Title\n\nA short paragraph.\n")
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 100
