from typing import Final, Literal

from onyx.error_handling.error_codes import OnyxErrorCode
from onyx.error_handling.exceptions import OnyxError

LLMModality = Literal["text", "image", "video", "pdf"]

INPUT_MODALITIES: Final[frozenset[str]] = frozenset({"text", "image", "video", "pdf"})
OUTPUT_MODALITIES: Final[frozenset[str]] = frozenset({"text"})
REQUIRED_MODALITY: Final[str] = "text"


def normalize_modalities(
    values: list[str] | None,
    *,
    allowed: frozenset[str],
    field_name: str,
) -> list[str] | None:
    """Validate and order a stored modality list. None means infer at read time."""
    if values is None:
        return None
    seen: set[str] = set()
    ordered: list[str] = []
    for raw in values:
        value = raw.strip().lower()
        if value not in allowed:
            raise OnyxError(
                OnyxErrorCode.BAD_REQUEST,
                f"{field_name} contains unsupported type {raw!r}",
            )
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    if REQUIRED_MODALITY not in seen:
        ordered.insert(0, REQUIRED_MODALITY)
    return ordered


def infer_input_modalities(*, supports_image: bool) -> list[str]:
    return ["text", "image"] if supports_image else ["text"]


def infer_output_modalities() -> list[str]:
    return ["text"]


def has_image_input(modalities: list[str] | None, *, inferred_image: bool) -> bool:
    if modalities is not None:
        return "image" in modalities
    return inferred_image
