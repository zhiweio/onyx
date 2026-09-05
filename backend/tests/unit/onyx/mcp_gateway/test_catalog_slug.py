import pytest
from pydantic import ValidationError

from onyx.server.features.mcp_catalog.models import CatalogEntryCreateRequest
from onyx.server.features.mcp_catalog.slug import catalog_slug_from_input


def test_package_name_becomes_catalog_slug() -> None:
    assert catalog_slug_from_input("@upstash/context7-mcp") == "upstash-context7-mcp"


def test_create_request_normalizes_slug() -> None:
    request = CatalogEntryCreateRequest(
        slug="@upstash/context7-mcp",
        pack_slug="generic_http",
        upstream_url="https://context7.liam.sh/mcp",
    )
    assert request.slug == "upstash-context7-mcp"


def test_empty_slug_is_rejected() -> None:
    with pytest.raises(ValidationError):
        CatalogEntryCreateRequest(
            slug="@@@",
            pack_slug="generic_http",
            upstream_url="https://example.com/mcp",
        )
