"""Prompt template substitution for Craft env vars / secrets.

Syntax mirrors the existing ``{{user.<key>}}`` prompt placeholders and the
GitHub Actions contexts: ``{{env.NAME}}`` and ``{{secrets.NAME}}`` both
resolve from the task's granted set. The distinction is documentation for
the prompt author — secrets should be referenced via ``{{secrets.NAME}}``.
"""

from __future__ import annotations

import re
from typing import Mapping

# Whitespace-tolerant, same identifier charset as env-var names.
_ENV_VAR_TEMPLATE_RE = re.compile(
    r"\{\{\s*(?:env|secrets)\.([A-Za-z_][A-Za-z0-9_]*)\s*\}\}"
)


def extract_env_var_references(prompt: str) -> list[str]:
    """Referenced names, unique, in first-appearance order."""
    seen: set[str] = set()
    names: list[str] = []
    for match in _ENV_VAR_TEMPLATE_RE.finditer(prompt):
        name = match.group(1)
        if name not in seen:
            seen.add(name)
            names.append(name)
    return names


def render_prompt_with_env_vars(
    prompt: str, values: Mapping[str, str]
) -> tuple[str, list[str]]:
    """Replace every ``{{env.X}}`` / ``{{secrets.X}}`` with its value.

    Returns ``(rendered_prompt, unresolved_names)``. Unresolved references
    are left in place; the executor fails the run on them so a missing
    grant is never silently sent to the agent as literal template text.
    """
    unresolved: list[str] = []

    def _replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name in values:
            return values[name]
        if name not in unresolved:
            unresolved.append(name)
        return match.group(0)

    return _ENV_VAR_TEMPLATE_RE.sub(_replace, prompt), unresolved
