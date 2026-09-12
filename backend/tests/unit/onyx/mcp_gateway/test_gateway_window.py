from datetime import datetime, timezone

import pytest

from onyx.error_handling.exceptions import OnyxError
from onyx.server.features.mcp_catalog.api import (
    _exclusive_utc_end,
    _parse_window,
)


def test_exclusive_utc_end_keeps_utc_midnight() -> None:
    midnight = datetime(2026, 9, 13, tzinfo=timezone.utc)
    assert _exclusive_utc_end(midnight) == midnight


def test_exclusive_utc_end_snaps_local_end_of_day() -> None:
    # Default picker in UTC+8: end of UTC calendar day 12 Sep.
    local_end = datetime(2026, 9, 12, 15, 59, 59, 999000, tzinfo=timezone.utc)
    assert _exclusive_utc_end(local_end) == datetime(
        2026, 9, 13, tzinfo=timezone.utc
    )


def test_parse_window_includes_late_utc_calls() -> None:
    start, end = _parse_window(
        datetime(2026, 9, 6, 16, 0, tzinfo=timezone.utc),
        datetime(2026, 9, 12, 15, 59, 59, 999000, tzinfo=timezone.utc),
    )
    call = datetime(2026, 9, 12, 19, 14, 59, tzinfo=timezone.utc)
    assert start <= call < end
    assert end == datetime(2026, 9, 13, tzinfo=timezone.utc)


def test_parse_window_treats_naive_datetimes_as_utc() -> None:
    start, end = _parse_window(
        datetime(2026, 9, 6, 16, 0),
        datetime(2026, 9, 12, 15, 59, 59, 999000),
    )
    assert start.tzinfo == timezone.utc
    assert end == datetime(2026, 9, 13, tzinfo=timezone.utc)


def test_parse_window_rejects_empty_bounds() -> None:
    with pytest.raises(OnyxError):
        _parse_window(None, datetime(2026, 9, 13, tzinfo=timezone.utc))


def test_parse_window_rejects_inverted_bounds() -> None:
    with pytest.raises(OnyxError):
        _parse_window(
            datetime(2026, 9, 13, tzinfo=timezone.utc),
            datetime(2026, 9, 12, 15, 59, 59, 999000, tzinfo=timezone.utc),
        )
