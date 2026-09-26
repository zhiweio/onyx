"""Inbound content screening for egress responses (QM's fail-open-with-labels).

Research lanes fetch external pages; whatever those pages contain flows
straight into the agent's context. This module screens response bodies for
prompt-injection patterns before the sandbox ever sees them, in three modes:

* ``off``     — nothing is inspected.
* ``shadow``  — every screenable response is classified and the verdict is
  logged; bodies are untouched. Run here first and review the hit rate before
  switching to ``enforce``.
* ``enforce`` — a ``suspicious`` body is replaced with a quarantine notice.
  A human-release flow for quarantined content (an approval card that
  re-fetches the URL) is a deliberate follow-up.

Failure philosophy: screening is additive. Any error inside the screener
degrades to ``unscreened`` and the body flows unchanged — labelled in the
log, never blocking egress.
"""

from __future__ import annotations

import os
import re
from enum import Enum

from onyx.utils.logger import setup_logger

logger = setup_logger()


def _screening_mode_from_env() -> str:
    mode = os.environ.get("CRAFT_CONTENT_SCREENING_MODE", "shadow").strip().lower()
    return mode if mode in {"off", "shadow", "enforce"} else "shadow"


CRAFT_CONTENT_SCREENING_MODE = _screening_mode_from_env()
CRAFT_CONTENT_SCREEN_MAX_BYTES = 2 * 1024 * 1024


class ScreeningVerdict(str, Enum):
    CLEAN = "clean"
    SUSPICIOUS = "suspicious"
    UNSCREENED = "unscreened"


_SCREENABLE_CONTENT_TYPES = ("text/", "application/json", "application/xml")
# SSE bodies are the agent's own streamed completions; they must keep
# streaming incrementally and can't be meaningfully screened mid-stream.
_NON_SCREENABLE_CONTENT_TYPES = ("text/event-stream",)

# Heuristic injection patterns, tuned for research pages. Each is an
# instruction-style imperative aimed at the model rather than the reader.
# Names surface in quarantine rows/cards so a reviewer knows what fired.
_INJECTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (name, re.compile(pattern, re.IGNORECASE))
    for name, pattern in (
        (
            "ignore_previous_instructions",
            r"ignore (all |any |the )?(previous|prior|above) (instructions|prompts|rules)",
        ),
        (
            "disregard_instructions",
            r"disregard (all |the )?(previous|prior|above) (instructions|prompts|rules)",
        ),
        ("forget_everything", r"forget (everything|all) (you|above|from earlier)"),
        ("new_system_instructions", r"(new|updated) (system )?(instructions|prompt):"),
        ("you_are_now", r"you are now (a|an|the) "),
        (
            "system_prompt_assignment",
            r"(system|assistant|developer)\s*(prompt|message)\s*[:=]",
        ),
        (
            "end_of_system_prompt",
            r"end (of )?(the )?(system|developer) (prompt|message)",
        ),
        ("special_token_markers", r"<\|(im_start|im_end|system|endoftext)\|>"),
        ("reveal_system_prompt", r"reveal (your|the) (system )?(prompt|instructions)"),
        (
            "print_system_prompt",
            r"(print|repeat|output) (your|the) (system )?(prompt|instructions)",
        ),
        ("conceal_from_user", r"do not (tell|inform|reveal) (the user|anyone)"),
    )
)

# Signals a page is aggressively trying to steer agent behaviour; one match
# flags the body. Kept deliberately cheap and readable — the shadow mode's
# job is to measure this list's hit rate before anything is enforced.


def content_type_screenable(content_type: str | None) -> bool:
    """Whether a response's content type is text the model could ingest."""
    if not isinstance(content_type, str) or not content_type:
        return False
    lowered = content_type.lower()
    if any(lowered.startswith(prefix) for prefix in _NON_SCREENABLE_CONTENT_TYPES):
        return False
    return any(lowered.startswith(prefix) for prefix in _SCREENABLE_CONTENT_TYPES)


def matched_pattern_names(text: str) -> list[str]:
    """Names of the heuristics the body tripped. Fail-open: errors → []."""
    if not text:
        return []
    try:
        return [name for name, pattern in _INJECTION_PATTERNS if pattern.search(text)]
    except Exception:
        logger.warning("content_screening_pattern_match_error", exc_info=True)
        return []


def screen_text(text: str) -> ScreeningVerdict:
    """Classify a response body. Pure and synchronous; never raises."""
    return (
        ScreeningVerdict.SUSPICIOUS
        if matched_pattern_names(text)
        else ScreeningVerdict.CLEAN
    )


def quarantine_notice(reason: str) -> str:
    """The body an ``enforce``-mode quarantine serves instead of the content."""
    return (
        "[Onyx inbound content screener] This content was quarantined before "
        f"it reached your context ({reason}). Do not retry this URL. If the "
        "content is required, ask the user to review and approve it."
    )
