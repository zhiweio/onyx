import pytest

from onyx.db.system_catalog.constants import (
    TAG_MAX,
    TAGS_MAX_COUNT,
    normalize_tags,
)
from onyx.error_handling.error_codes import OnyxErrorCode
from onyx.error_handling.exceptions import OnyxError
from onyx.server.features.system_catalog.models import SystemSkillPatchRequest


def test_normalize_tags_trims_dedupes_and_sorts() -> None:
    assert normalize_tags([" Route ", "chart", "route", ""]) == ["chart", "route"]


def test_normalize_tags_rejects_overlong() -> None:
    with pytest.raises(OnyxError) as caught:
        normalize_tags(["x" * (TAG_MAX + 1)])
    assert caught.value.error_code is OnyxErrorCode.INVALID_INPUT


def test_normalize_tags_rejects_too_many() -> None:
    with pytest.raises(OnyxError) as caught:
        normalize_tags([f"t{index}" for index in range(TAGS_MAX_COUNT + 1)])
    assert caught.value.error_code is OnyxErrorCode.INVALID_INPUT


def test_skill_patch_request_normalizes_tags() -> None:
    request = SystemSkillPatchRequest(tags=[" Route ", "route", "Chart"])
    assert request.tags == ["chart", "route"]
