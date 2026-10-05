"""Turn-failure classification, shared by the kernel and the gates.

One place decides whether a failed turn deserves an automatic re-drive.
The markers below all leave the workspace intact, so re-driving the same
phase/lane prompt is safe. Everything else is permanent: the failure
reaches the user, and retrying would only repeat it.
"""

from __future__ import annotations

# Substring signatures of transient turn failures.
_TRANSIENT_TURN_ERROR_MARKERS: tuple[str, ...] = (
    "upstream_error",
    "upstream llm request failed",
    "temporarily rate limited",
    "rate_limit_error",
    "did not respond in time",
    "hard time cap exceeded",
    "before opencode returned a final response",
    "ended before the agent returned a final response",
    "event bus closed",
    "prompt_async failed",
    # A reaped lane whose driver was lost (API restart): the work state is
    # on disk, so a re-drive is safe.
    "lane inactive",
)


def is_transient_turn_error(error_detail: str | None) -> bool:
    """Whether one failed turn is worth one automatic retry."""
    if not error_detail:
        return False
    lowered = error_detail.lower()
    return any(marker in lowered for marker in _TRANSIENT_TURN_ERROR_MARKERS)
