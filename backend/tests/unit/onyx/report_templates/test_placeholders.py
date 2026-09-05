from onyx.report_templates.placeholders import (
    merge_placeholder_schema,
    normalize_placeholder_schema,
    spec_from_name,
    table_collections,
)


def test_dotted_name_defaults_to_table() -> None:
    spec = spec_from_name("findings.title")
    assert spec["kind"] == "table"
    assert spec["required"] is True


def test_plain_name_defaults_to_text() -> None:
    spec = spec_from_name("entity_name")
    assert spec["kind"] == "text"


def test_normalize_accepts_bare_names() -> None:
    schema = normalize_placeholder_schema(["entity_name", "findings.title"])
    assert schema[0]["name"] == "entity_name"
    assert schema[1]["kind"] == "table"


def test_merge_keeps_file_names_and_drops_unknown_overlay() -> None:
    overlay = [
        spec_from_name("entity_name"),
        {
            "name": "entity_name",
            "kind": "text",
            "required": True,
            "description": "Legal name",
            "example": "Acme",
        },
        spec_from_name("ghost"),
    ]
    merged = merge_placeholder_schema(["entity_name", "period"], overlay)
    assert [item["name"] for item in merged] == ["entity_name", "period"]
    assert merged[0]["description"] == "Legal name"
    assert merged[1]["description"] == ""


def test_table_collections_groups_dotted_fields() -> None:
    schema = normalize_placeholder_schema(
        ["entity_name", "findings.title", "findings.severity"]
    )
    assert table_collections(schema) == {
        "findings": ["title", "severity"],
    }
