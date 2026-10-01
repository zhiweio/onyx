"""Unit tests for the doc permission sync runner's pure decision logic."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from onyx.background.celery.tasks.doc_permission_syncing.tasks import (
    _connector_supports_perm_sync,
    _is_perm_sync_due,
    element_update_permissions,
)
from onyx.connectors.interfaces import SlimConnector, SlimConnectorWithPermSync
from onyx.db.enums import ConnectorCredentialPairStatus


class _FakeConnector(SlimConnector):
    def slimRetrieveAllDocuments(self):  # pragma: no cover - abstract stub
        raise NotImplementedError


class _PermSyncConnector(_FakeConnector, SlimConnectorWithPermSync):
    def retrieve_all_slim_docs_perm_sync(self, start=None, end=None, callback=None):
        raise NotImplementedError


def _cc_pair(
    *,
    status=ConnectorCredentialPairStatus.ACTIVE,
    last_index=datetime(2026, 1, 1, tzinfo=timezone.utc),
    last_perm_sync=None,
) -> Any:
    """Attribute-compatible stand-in; the runner only reads these fields."""
    return SimpleNamespace(
        status=status,
        last_successful_index_time=last_index,
        last_time_perm_sync=last_perm_sync,
        connector=SimpleNamespace(source="google_drive", input_type="load_state"),
    )


def test_perm_sync_support_requires_slim_with_perm_sync() -> None:
    pair = _cc_pair()

    def _identify(source, input_type=None):
        del source, input_type
        return _PermSyncConnector

    def _identify_plain(source, input_type=None):
        del source, input_type
        return _FakeConnector

    module = "onyx.background.celery.tasks.doc_permission_syncing.tasks"
    with patch(f"{module}.identify_connector_class", _identify):
        assert _connector_supports_perm_sync(pair) is True
    with patch(f"{module}.identify_connector_class", _identify_plain):
        assert _connector_supports_perm_sync(pair) is False


def test_perm_sync_due_rules() -> None:
    now = datetime.now(timezone.utc)

    # Never indexed → not due (no documents to update yet).
    assert _is_perm_sync_due(_cc_pair(last_index=None)) is False
    # Not active → never due.
    assert (
        _is_perm_sync_due(_cc_pair(status=ConnectorCredentialPairStatus.PAUSED))
        is False
    )
    # Never synced → due.
    assert _is_perm_sync_due(_cc_pair()) is True
    # Synced recently → not due.
    assert _is_perm_sync_due(_cc_pair(last_perm_sync=now - timedelta(hours=1))) is False
    # Synced past the interval → due again.
    assert _is_perm_sync_due(_cc_pair(last_perm_sync=now - timedelta(hours=25))) is True


def test_element_update_dispatches_by_type() -> None:
    from onyx.access.models import DocExternalAccess, ExternalAccess, NodeExternalAccess

    access = ExternalAccess(
        external_user_emails={"a@b.c"}, external_user_group_ids=set(), is_public=False
    )
    doc_perm = DocExternalAccess(external_access=access, doc_id="doc-1")
    node_perm = NodeExternalAccess(
        external_access=access, raw_node_id="node-1", source="google_drive"
    )

    with (
        patch(
            "onyx.background.celery.tasks.doc_permission_syncing.tasks"
            "._update_document_permissions"
        ) as doc_fn,
        patch(
            "onyx.background.celery.tasks.doc_permission_syncing.tasks"
            "._update_hierarchy_node_permissions"
        ) as node_fn,
    ):
        element_update_permissions("tenant-1", doc_perm, "google_drive", 1, 2)
        doc_fn.assert_called_once_with("tenant-1", doc_perm)
        node_fn.assert_not_called()

        doc_fn.reset_mock()
        element_update_permissions("tenant-1", node_perm, "google_drive", 1, 2)
        node_fn.assert_called_once_with("tenant-1", node_perm, "google_drive")
        doc_fn.assert_not_called()
