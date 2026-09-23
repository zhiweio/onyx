"""Run-time masking of granted secret values.

GitHub-Actions semantics: a secret used by a run is redacted from the run's
persisted transcript, summaries and error details. The executor masks every
sandbox event before it reaches streaming state or persistence, so this is
the single choke point.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from pydantic import BaseModel

from onyx.utils.logger import setup_logger

logger = setup_logger()

MASKED_SECRET = "***"


class SecretMasker:
    """Replaces known secret plaintexts with ``***`` in any text.

    Values are matched longest-first so two secrets sharing a prefix cannot
    shadow each other. Matching is exact-case substring replacement.
    """

    def __init__(self, secret_values: list[str] | tuple[str, ...]) -> None:
        # Longest first: replacing a shorter overlapping value first would
        # leave fragments of the longer one unmasked.
        self._secrets = sorted(
            {value for value in secret_values if value}, key=len, reverse=True
        )

    @property
    def active(self) -> bool:
        """False when there is nothing to mask — callers skip the walk."""
        return bool(self._secrets)

    def mask(self, text: str) -> str:
        for secret in self._secrets:
            if secret in text:
                text = text.replace(secret, MASKED_SECRET)
        return text


def mask_sandbox_event[T](event: T, masker: SecretMasker) -> T:
    """Return ``event`` with secret values masked in every string it holds.

    Structural walk over pydantic models, dataclasses, dicts and sequences,
    so new event fields are covered without changes here. Sub-objects are
    copied only when a mask actually applies; untouched branches keep their
    identity. Never raises — on any copy failure the original event is
    returned and the failure is logged.
    """
    if not masker.active:
        return event
    try:
        return _mask_value(event, masker)  # type: ignore[return-value]
    except Exception:
        logger.exception("Failed to mask a sandbox event; masking skipped")
        return event


def _mask_value(value: Any, masker: SecretMasker) -> Any:
    if isinstance(value, str):
        return masker.mask(value)
    if isinstance(value, BaseModel):
        updates: dict[str, Any] = {}
        for field_name in type(value).model_fields:
            field_value = getattr(value, field_name)
            masked = _mask_value(field_value, masker)
            if masked is not field_value:
                updates[field_name] = masked
        if not updates:
            return value
        return value.model_copy(update=updates)
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        changes = {
            field.name: masked
            for field in dataclasses.fields(value)
            if (masked := _mask_value(getattr(value, field.name), masker))
            is not getattr(value, field.name)
        }
        if not changes:
            return value
        return dataclasses.replace(value, **changes)
    if isinstance(value, dict):
        # Keys stay untouched: they are structural, never payload text.
        return {key: _mask_value(item, masker) for key, item in value.items()}
    if isinstance(value, list):
        return [_mask_value(item, masker) for item in value]
    if isinstance(value, tuple):
        masked = tuple(_mask_value(item, masker) for item in value)
        return masked if masked != value else value
    return value
