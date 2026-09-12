"""SqlCatalog bootstrap. Metadata is not stored in a tenant schema."""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from pyiceberg.catalog import Catalog, load_catalog
from pyiceberg.exceptions import NamespaceAlreadyExistsError, TableAlreadyExistsError
from sqlalchemy import create_engine, text

from onyx.configs.app_configs import (
    AWS_REGION_NAME,
    MCP_ICEBERG_CATALOG_SCHEMA,
    MCP_ICEBERG_CATALOG_URI,
    MCP_ICEBERG_NAMESPACE,
    MCP_ICEBERG_WAREHOUSE,
    S3_AWS_ACCESS_KEY_ID,
    S3_AWS_SECRET_ACCESS_KEY,
    S3_ENDPOINT_URL,
)
from onyx.db.engine.sql_engine import SYNC_DB_API, build_connection_string
from onyx.mcp_gateway.lake.schemas import TABLES
from onyx.utils.logger import setup_logger

logger = setup_logger()

_lock = threading.RLock()
_catalog: Catalog | None = None
_ready = False


def _file_warehouse(uri: str) -> str:
    if uri.startswith("file://"):
        path = Path(uri.removeprefix("file://"))
        path.mkdir(parents=True, exist_ok=True)
        return f"file://{path}"
    return uri


def _catalog_uri() -> str:
    uri = os.environ.get("MCP_ICEBERG_CATALOG_URI") or MCP_ICEBERG_CATALOG_URI
    if uri:
        return uri
    return build_connection_string(db_api=SYNC_DB_API)


def _warehouse() -> str:
    return _file_warehouse(
        os.environ.get("MCP_ICEBERG_WAREHOUSE") or MCP_ICEBERG_WAREHOUSE
    )


def _ensure_catalog_schema(uri: str) -> None:
    if not uri.startswith("postgresql"):
        return
    engine = create_engine(uri)
    schema = MCP_ICEBERG_CATALOG_SCHEMA
    with engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
    engine.dispose()


def _postgres_uri_with_search_path(uri: str) -> str:
    if not uri.startswith("postgresql"):
        return uri
    sep = "&" if "?" in uri else "?"
    return f"{uri}{sep}{urlencode({'options': f'-csearch_path={MCP_ICEBERG_CATALOG_SCHEMA}'})}"


def _s3_properties() -> dict[str, str]:
    props: dict[str, str] = {}
    if S3_ENDPOINT_URL:
        props["s3.endpoint"] = S3_ENDPOINT_URL
        props["s3.path-style-access"] = "true"
        props["s3.region"] = AWS_REGION_NAME
    if S3_AWS_ACCESS_KEY_ID:
        props["s3.access-key-id"] = S3_AWS_ACCESS_KEY_ID
    if S3_AWS_SECRET_ACCESS_KEY:
        props["s3.secret-access-key"] = S3_AWS_SECRET_ACCESS_KEY
    return props


def _catalog_properties() -> dict[str, Any]:
    uri = _catalog_uri()
    _ensure_catalog_schema(uri)
    warehouse = _warehouse()
    props: dict[str, Any] = {
        "uri": _postgres_uri_with_search_path(uri),
        "warehouse": warehouse,
        "init_catalog_tables": "true",
    }
    props.update(_s3_properties())
    return props


def get_catalog() -> Catalog:
    global _catalog
    with _lock:
        if _catalog is None:
            _catalog = load_catalog("mcp_gateway", type="sql", **_catalog_properties())
        return _catalog


def table_ident(name: str) -> str:
    return f"{MCP_ICEBERG_NAMESPACE}.{name}"


def ensure_mcp_iceberg_tables() -> None:
    """Create the namespace and star tables if they are missing."""
    global _ready
    if _ready:
        return
    with _lock:
        if _ready:
            return
        catalog = get_catalog()
        try:
            catalog.create_namespace(MCP_ICEBERG_NAMESPACE)
        except NamespaceAlreadyExistsError:
            pass
        for name, schema, spec in TABLES:
            ident = table_ident(name)
            try:
                catalog.create_table(ident, schema=schema, partition_spec=spec)
            except TableAlreadyExistsError:
                pass
        _ready = True
        logger.info(
            "MCP Iceberg tables ready in %s at %s",
            MCP_ICEBERG_NAMESPACE,
            _warehouse(),
        )


def reset_lake_for_tests() -> None:
    """Drop the process-wide catalog so a test can point at a temp warehouse."""
    global _catalog, _ready
    with _lock:
        _catalog = None
        _ready = False
