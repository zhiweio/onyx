"""Reject secrets and one-off instructions before they enter long-term memory."""

from __future__ import annotations

import re

_SECRET_RE = re.compile(
    r"(?i)("
    r"sk-[a-z0-9]{10,}"
    r"|api[_-]?key\s*[:=]"
    r"|bearer\s+[a-z0-9._\-]{12,}"
    r"|password\s*[:=]"
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----"
    r"|AKIA[0-9A-Z]{12,}"
    r")"
)
_PII_RE = re.compile(
    r"("
    r"\b\d{3}-\d{2}-\d{4}\b"
    r"|\b(?:\d[ -]*?){13,19}\b"
    r")"
)
_ONE_OFF_RE = re.compile(
    r"(?i)^(please |帮我|请)?(do |run |write |fix |generate |create |打开|运行|写一份)"
)


def reject_reason(text: str) -> str | None:
    stripped = text.strip()
    if len(stripped) < 12:
        return "too_short"
    if _SECRET_RE.search(stripped):
        return "secret"
    if _PII_RE.search(stripped):
        return "pii"
    if _ONE_OFF_RE.match(stripped) and len(stripped) < 80:
        return "one_off"
    return None
