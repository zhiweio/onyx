from io import BytesIO

from PIL import Image as PILImage

from onyx.server.features.build.session.md_document import markdown_to_html
from onyx.server.features.build.session.md_to_pdf import markdown_to_pdf_bytes


def _tiny_png() -> bytes:
    buffer = BytesIO()
    PILImage.new("RGB", (64, 48), (20, 80, 160)).save(buffer, format="PNG")
    return buffer.getvalue()


def test_markdown_to_pdf_bytes_writes_pdf_header() -> None:
    pdf = markdown_to_pdf_bytes("# Title\n\nA short paragraph.\n")
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 100


def test_markdown_to_pdf_bytes_uses_cjk_font_for_chinese() -> None:
    pdf = markdown_to_pdf_bytes("# 君禾泵业\n\n财务风险分析。\n")
    assert pdf.startswith(b"%PDF")
    assert b"STSong" in pdf


def test_markdown_to_pdf_renders_gfm_table() -> None:
    pdf = markdown_to_pdf_bytes("| 项目 | 金额 |\n|---|---|\n| 收入 | 100 |\n")
    assert pdf.startswith(b"%PDF")
    assert b"STSong" in pdf
    assert len(pdf) > 200


def test_markdown_to_pdf_renders_nested_list() -> None:
    pdf = markdown_to_pdf_bytes("- one\n  - nested\n- two\n")
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 100


def test_markdown_to_pdf_renders_footnotes() -> None:
    pdf = markdown_to_pdf_bytes("See note.[^1]\n\n[^1]: The note body.\n")
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 100


def test_markdown_to_pdf_escapes_angle_brackets() -> None:
    pdf = markdown_to_pdf_bytes("A < B and C > D\n")
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 100


def test_markdown_to_pdf_embeds_local_image() -> None:
    png = _tiny_png()
    with_image = markdown_to_pdf_bytes(
        "![timeline](figures/competitor_timeline.png)\n",
        image_loader=lambda _src: png,
    )
    without_image = markdown_to_pdf_bytes(
        "![timeline](figures/competitor_timeline.png)\n"
    )
    assert with_image.startswith(b"%PDF")
    assert b"/Image" in with_image
    assert len(with_image) > len(without_image)


def test_markdown_to_html_includes_cjk_and_table() -> None:
    html = markdown_to_html("# 标题\n\n| A | B |\n|---|---|\n| 1 | 2 |\n")
    assert "zh-CN" in html
    assert "标题" in html
    assert "<table" in html
    assert "<th>" in html
