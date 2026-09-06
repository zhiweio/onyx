"""Normalize a catalog slug from admin input.

Admins often paste a package name such as ``@upstash/context7-mcp``. The
catalog key must stay URL-safe and unique, so this turns that input into
``upstash-context7-mcp``.
"""

import re

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


def catalog_slug_from_input(value: str) -> str:
    slug = value.strip().lower()
    if slug.startswith("@"):
        slug = slug[1:]
    slug = re.sub(r"[^a-z0-9_-]+", "-", slug)
    slug = slug.strip("-_")
    slug = slug[:128]
    if not slug or not _SLUG_RE.match(slug):
        raise ValueError(
            "Slug must start with a letter or digit and use only "
            "letters, digits, '_' and '-'."
        )
    return slug
