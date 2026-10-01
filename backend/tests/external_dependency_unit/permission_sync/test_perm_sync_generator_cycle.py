"""Full generator-cycle test for the CE doc permission sync runner.

Runs ``connector_permission_sync_generator_task`` against real Postgres and
Redis with a stubbed connector: due cc pair → slim docs → external access
upserts → completed DocPermissionSyncAttempt, plus the schedule stamp on
``last_time_perm_sync``. The document-index write is stubbed (the index
update path itself is covered by the shared metadata-update tests).
"""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from onyx.access.models import ExternalAccess
from onyx.background.celery.tasks.doc_permission_syncing import (
    tasks as perm_sync_tasks,
)
from onyx.configs.constants import DocumentSource
from onyx.connectors.interfaces import (
    GenerateSlimDocumentOutput,
    SlimConnectorWithPermSync,
)
from onyx.connectors.models import SlimDocument
from onyx.db.connector_credential_pair import get_connector_credential_pair_from_id
from onyx.db.enums import (
    AccessType,
    ConnectorCredentialPairStatus,
    PermissionSyncStatus,
)
from onyx.db.permission_sync_attempt import (
    get_latest_doc_permission_sync_attempt_for_cc_pair,
)
from shared_configs.configs import POSTGRES_DEFAULT_SCHEMA_STANDARD_VALUE
from tests.external_dependency_unit.permission_sync.conftest import (
    create_test_connector_credential_pair,
)

TASKS_MODULE = "onyx.background.celery.tasks.doc_permission_syncing.tasks"
# The external-dependency database runs in the standard single-tenant schema.
TENANT_ID = POSTGRES_DEFAULT_SCHEMA_STANDARD_VALUE


class StubPermSyncConnector(SlimConnectorWithPermSync):
    """Yields two batches of slim docs carrying external access."""

    def load_credentials(self, credentials: dict[str, Any]) -> None:
        pass

    def retrieve_all_slim_docs_perm_sync(
        self,
        start: float | None = None,
        end: float | None = None,
        callback: Any = None,
    ) -> GenerateSlimDocumentOutput:
        del start, end, callback
        yield [
            SlimDocument(
                id="perm-sync-doc-1",
                external_access=ExternalAccess(
                    external_user_emails={"viewer@example.com"},
                    external_user_group_ids=set(),
                    is_public=False,
                ),
            ),
            SlimDocument(
                id="perm-sync-doc-2",
                external_access=ExternalAccess.public(),
            ),
        ]
        yield [
            SlimDocument(
                id="perm-sync-doc-3",
                external_access=ExternalAccess(
                    external_user_emails={"admin@example.com"},
                    external_user_group_ids={"admins"},
                    is_public=False,
                ),
            )
        ]


def _create_cc_pair_with_index_history(db_session: Session) -> int:
    """create_test_connector_credential_pair + a successful index stamp so
    the pair passes the due checks."""
    pair = create_test_connector_credential_pair(
        db_session, source=DocumentSource.FEISHU, access_type=AccessType.PRIVATE
    )
    pair.last_successful_index_time = datetime.now(timezone.utc)
    pair.status = ConnectorCredentialPairStatus.ACTIVE
    db_session.commit()
    return pair.id


def test_generator_cycle_completes_attempt(db_session: Session) -> None:
    from unittest.mock import patch

    cc_pair_id = _create_cc_pair_with_index_history(db_session)
    updated_docs: list[str] = []

    def _stub_instantiate(
        db_session, source, input_type, connector_specific_config, credential
    ):
        del db_session, source, input_type, connector_specific_config, credential
        return StubPermSyncConnector()

    def _stub_update_document_permissions(tenant_id: str, permissions: Any) -> None:
        del tenant_id
        updated_docs.append(permissions.doc_id)

    with (
        patch(f"{TASKS_MODULE}.instantiate_connector", _stub_instantiate),
        patch(
            f"{TASKS_MODULE}._update_document_permissions",
            _stub_update_document_permissions,
        ),
    ):
        perm_sync_tasks.connector_permission_sync_generator_task.apply(
            kwargs=dict(cc_pair_id=cc_pair_id, tenant_id=TENANT_ID)
        )

    # Every slim doc's external access reached the updater, in batch order.
    assert sorted(updated_docs) == [
        "perm-sync-doc-1",
        "perm-sync-doc-2",
        "perm-sync-doc-3",
    ]

    # The attempt closed out successfully with the doc count recorded.
    attempt = get_latest_doc_permission_sync_attempt_for_cc_pair(db_session, cc_pair_id)
    assert attempt is not None
    assert attempt.status is PermissionSyncStatus.SUCCESS
    assert attempt.total_docs_synced == 3
    assert attempt.docs_with_permission_errors == 0

    # The schedule marker moved, so the sweep won't re-enqueue immediately.
    refreshed = get_connector_credential_pair_from_id(
        db_session=db_session, cc_pair_id=cc_pair_id
    )
    assert refreshed is not None
    assert refreshed.last_time_perm_sync is not None


def test_generator_failure_marks_attempt_failed(db_session: Session) -> None:
    from unittest.mock import patch

    cc_pair_id = _create_cc_pair_with_index_history(db_session)

    def _boom(db_session, source, input_type, connector_specific_config, credential):
        del db_session, source, input_type, connector_specific_config, credential
        raise RuntimeError("connector exploded")

    with patch(f"{TASKS_MODULE}.instantiate_connector", _boom):
        perm_sync_tasks.connector_permission_sync_generator_task.apply(
            kwargs=dict(cc_pair_id=cc_pair_id, tenant_id=TENANT_ID)
        )

    attempt = get_latest_doc_permission_sync_attempt_for_cc_pair(db_session, cc_pair_id)
    assert attempt is not None
    assert attempt.status is PermissionSyncStatus.FAILED
    assert "connector exploded" in (attempt.error_message or "")
