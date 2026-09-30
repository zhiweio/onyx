"""SAP connector via generic OData: turns entity sets into documents.

Rather than protocol-specific RFC/BAPI bindings, this connector speaks
OData V2/V4 — SAP's standard REST surface (S/4HANA Gateway, Fiori
services). Each configured entity set becomes one document per batch of
rows; customers point it at the specific services they need (e.g.
A_SupplierInvoice, API_SUPPLIER_OSRV).

Credentials: ``sap_odata_base_url`` (e.g.
``https://sap.example.com/sap/opu/odata/sap/API_SUPPLIER_SRV``) and
either ``sap_odata_user``/``sap_odata_password`` (basic) or
``sap_odata_apikey``. Metadata ``sap_odata_entity_sets`` (JSON list)
selects what to index.
"""

from __future__ import annotations

import json
from typing import Any

import requests

from onyx.configs.app_configs import INDEX_BATCH_SIZE
from onyx.configs.constants import DocumentSource
from onyx.connectors.interfaces import (
    GenerateDocumentsOutput,
    LoadConnector,
    PollConnector,
    SecondsSinceUnixEpoch,
)
from onyx.connectors.models import (
    ConnectorMissingCredentialError,
    Document,
    TextSection,
)
from onyx.utils.logger import setup_logger

logger = setup_logger()


def _extract_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    """OData V2 wraps payloads as {d: {results: [...]}}; V4 uses a bare
    list under the entity name or the top level."""
    if "d" in data:
        inner = data["d"]
        if isinstance(inner, dict) and "results" in inner:
            return list(inner["results"])
        return list(inner) if isinstance(inner, list) else [inner]
    for value in data.values():
        if isinstance(value, list):
            return list(value)
    return [data]


def _row_to_lines(row: dict[str, Any]) -> str:
    lines: list[str] = []
    for key, value in row.items():
        if key.startswith("__") or key in ("__metadata",):
            continue
        if isinstance(value, (dict, list)):
            continue
        lines.append(f"{key}: {value}")
    return "\n".join(lines)


class SapODataConnector(LoadConnector, PollConnector):
    def __init__(self, batch_size: int = INDEX_BATCH_SIZE) -> None:
        self.batch_size = batch_size
        self._base_url: str | None = None
        self._user: str | None = None
        self._password: str | None = None
        self._apikey: str | None = None
        self._entity_sets: list[str] = []

    def load_credentials(self, credentials: dict[str, Any]) -> dict[str, Any] | None:
        self._base_url = str(credentials["sap_odata_base_url"]).rstrip("/")
        self._user = credentials.get("sap_odata_user")
        self._password = credentials.get("sap_odata_password")
        self._apikey = credentials.get("sap_odata_apikey")
        raw_sets = credentials.get("sap_odata_entity_sets") or '[]'
        if isinstance(raw_sets, str):
            try:
                raw_sets = json.loads(raw_sets)
            except json.JSONDecodeError:
                raw_sets = [s.strip() for s in raw_sets.split(",") if s.strip()]
        self._entity_sets = [str(s) for s in raw_sets]
        return None

    def _session(self) -> requests.Session:
        if self._base_url is None:
            raise ConnectorMissingCredentialError("SAP OData")
        session = requests.Session()
        if self._apikey:
            session.headers["apikey"] = self._apikey
        elif self._user and self._password is not None:
            session.auth = (self._user, self._password)
        session.headers["Accept"] = "application/json"
        return session

    def _fetch_entity(self, session: requests.Session, entity: str) -> list[dict[str, Any]]:
        resp = session.get(
            f"{self._base_url}/{entity}",
            params={"$top": 5000, "$format": "json"},
            timeout=60,
        )
        if resp.status_code != 200:
            logger.warning("SAP OData %s -> %s", entity, resp.status_code)
            return []
        return _extract_rows(resp.json())

    def _load(self, start: float | None = None, end: float | None = None) -> GenerateDocumentsOutput:
        del start, end  # OData delta queries come with the poll upgrade
        session = self._session()
        batch: list[Document] = []
        for entity in self._entity_sets:
            rows = self._fetch_entity(session, entity)
            if not rows:
                continue
            text = "\n\n".join(_row_to_lines(row) for row in rows)
            batch.append(
                Document(
                    id=f"sap-odata-{entity}",
                    source=DocumentSource.SAP_ODATA,
                    semantic_identifier=f"SAP/{entity}",
                    title=f"SAP {entity}",
                    text=text,
                    sections=[TextSection(text=text)],
                    metadata={"entity_set": entity, "row_count": len(rows)},
                )
            )
            if len(batch) >= self.batch_size:
                yield batch
                batch = []
        if batch:
            yield batch

    def load_from_state(self) -> GenerateDocumentsOutput:
        return self._load()

    def poll_source(
        self, start: SecondsSinceUnixEpoch, end: SecondsSinceUnixEpoch
    ) -> GenerateDocumentsOutput:
        return self._load()
