from urllib.parse import quote

import pytest

from onyx.db.craft_project import sanitize_project_path
from onyx.error_handling.error_codes import OnyxErrorCode
from onyx.error_handling.exceptions import OnyxError
from onyx.server.features.craft_project.api import content_disposition


def test_sanitize_project_path_keeps_chinese_report_names() -> None:
    assert (
        sanitize_project_path("君禾股份_财报解读_2026H1.html")
        == "/君禾股份_财报解读_2026H1.html"
    )
    assert (
        sanitize_project_path("charts/营收趋势.png") == "/charts/营收趋势.png"
    )


def test_sanitize_project_path_strips_traversal_and_empty_segments() -> None:
    assert sanitize_project_path("../deck.pptx") == "/deck.pptx"
    assert sanitize_project_path("a/./b.md") == "/a/b.md"
    with pytest.raises(OnyxError) as exc:
        sanitize_project_path("../..")
    assert exc.value.error_code == OnyxErrorCode.INVALID_INPUT


def test_content_disposition_uses_rfc5987_for_chinese_names() -> None:
    assert content_disposition("rates.xlsx") == 'attachment; filename="rates.xlsx"'
    name = "君禾股份_财报解读_2026H1.html"
    assert content_disposition(name) == f"attachment; filename*=UTF-8''{quote(name, safe='')}"
