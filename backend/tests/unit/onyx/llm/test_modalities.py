import pytest

from onyx.error_handling.exceptions import OnyxError
from onyx.llm.modalities import (
    INPUT_MODALITIES,
    infer_input_modalities,
    infer_output_modalities,
    normalize_modalities,
)


def test_normalize_requires_text_and_dedupes() -> None:
    assert normalize_modalities(
        ["image", "IMAGE", "pdf"],
        allowed=INPUT_MODALITIES,
        field_name="input_modalities",
    ) == ["text", "image", "pdf"]


def test_normalize_rejects_unknown_type() -> None:
    with pytest.raises(OnyxError):
        normalize_modalities(
            ["text", "audio"],
            allowed=INPUT_MODALITIES,
            field_name="input_modalities",
        )


def test_infer_modalities() -> None:
    assert infer_input_modalities(supports_image=True) == ["text", "image"]
    assert infer_input_modalities(supports_image=False) == ["text"]
    assert infer_output_modalities() == ["text"]
