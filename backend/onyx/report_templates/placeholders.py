"""Typed placeholder contract for Word report templates.

Names always come from the document. Metadata (kind, description, example)
is merged on attach so a hand-uploaded file still works: a name with no
overlay is a required ``text`` token, or ``table`` when it is dotted
(``findings.title``).
"""

from __future__ import annotations

from typing import Any, Final, Literal, TypedDict

PlaceholderKind = Literal["text", "multiline", "date", "number", "table"]

PLACEHOLDER_KINDS: Final[frozenset[str]] = frozenset(
    {"text", "multiline", "date", "number", "table"}
)


class PlaceholderSpec(TypedDict):
    name: str
    kind: PlaceholderKind
    required: bool
    description: str
    example: str


def default_placeholder_kind(name: str) -> PlaceholderKind:
    """Dotted names address a repeating table row: ``{{findings.title}}``."""
    return "table" if "." in name else "text"


def spec_from_name(name: str) -> PlaceholderSpec:
    return PlaceholderSpec(
        name=name,
        kind=default_placeholder_kind(name),
        required=True,
        description="",
        example="",
    )


def normalize_placeholder_spec(raw: object) -> PlaceholderSpec:
    """Accept a stored dict or a bare name from an older row."""
    if isinstance(raw, str):
        return spec_from_name(raw)
    if not isinstance(raw, dict):
        raise ValueError("placeholder must be an object or a name")
    name = str(raw.get("name") or "").strip()
    if not name:
        raise ValueError("placeholder is missing a name")
    kind_raw = raw.get("kind") or default_placeholder_kind(name)
    kind: PlaceholderKind
    if kind_raw in PLACEHOLDER_KINDS:
        # The membership check above is the type gate; the cast is the
        # remaining Literal narrowing that typing cannot see.
        kind = kind_raw  # type: ignore[assignment]
    else:
        kind = default_placeholder_kind(name)
    return PlaceholderSpec(
        name=name,
        kind=kind,
        required=bool(raw.get("required", True)),
        description=str(raw.get("description") or ""),
        example=str(raw.get("example") or ""),
    )


def normalize_placeholder_schema(raw: list[Any] | None) -> list[PlaceholderSpec]:
    if not raw:
        return []
    return [normalize_placeholder_spec(item) for item in raw]


def placeholder_names(schema: list[PlaceholderSpec]) -> list[str]:
    return [item["name"] for item in schema]


def merge_placeholder_schema(
    names: list[str], overlay: list[PlaceholderSpec] | None = None
) -> list[PlaceholderSpec]:
    """Keep every name from the file; overlay only supplies metadata.

    A name in the file but missing from the overlay stays a required token.
    Overlay entries whose name is not in the file are dropped — the document
    is the source of truth.
    """
    by_name = {item["name"]: item for item in overlay or []}
    return [by_name[name] if name in by_name else spec_from_name(name) for name in names]


def table_collections(schema: list[PlaceholderSpec]) -> dict[str, list[str]]:
    """Map ``findings`` → ``['title', 'severity', ...]`` for table tokens."""
    collections: dict[str, list[str]] = {}
    for item in schema:
        if item["kind"] != "table" or "." not in item["name"]:
            continue
        collection, field = item["name"].split(".", 1)
        fields = collections.setdefault(collection, [])
        if field not in fields:
            fields.append(field)
    return collections
