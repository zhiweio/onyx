from types import SimpleNamespace
from typing import cast

from onyx.db.models import MCPServer
from onyx.server.features.mcp.gateway_bind import (
    catalog_credentials_to_connection_data,
    credentials_from_admin_config,
)
from onyx.server.features.mcp.models import MCPConnectionData


def _server_with_admin_config(config: MCPConnectionData) -> MCPServer:
    return cast(
        MCPServer,
        SimpleNamespace(
            admin_connection_config=SimpleNamespace(config=config),
        ),
    )


def test_credentials_from_admin_config_reads_bearer_and_extra_headers() -> None:
    server = _server_with_admin_config(
        MCPConnectionData(
            headers={
                "Authorization": "Bearer secret-token",
                "X-Org": "acme",
            },
            api_token="secret-token",
        )
    )
    assert credentials_from_admin_config(server) == {
        "api_key": "secret-token",
        "extra_headers": {"X-Org": "acme"},
    }


def test_credentials_from_admin_config_empty_without_config() -> None:
    server = cast(MCPServer, SimpleNamespace(admin_connection_config=None))
    assert credentials_from_admin_config(server) == {}


def test_catalog_credentials_round_trip_preserves_oauth_fields() -> None:
    existing = MCPConnectionData(
        headers={"Authorization": "Bearer old"},
        api_token="old",
        tokens={"access_token": "oauth"},
    )
    merged = catalog_credentials_to_connection_data({"api_key": "new-key"}, existing)
    assert merged["headers"]["Authorization"] == "Bearer new-key"
    assert merged["api_token"] == "new-key"
    assert merged["tokens"] == {"access_token": "oauth"}
