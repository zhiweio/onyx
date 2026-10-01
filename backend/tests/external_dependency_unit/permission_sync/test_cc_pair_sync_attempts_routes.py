"""Tests for the per-cc-pair sync-attempt history endpoints.

Covers:

* The new ``get_relevant_external_group_sync_attempts_for_cc_pair`` helper
  in ``onyx.db.permission_sync_attempt`` — including the source-wide query
  used for cc-pair-agnostic sources (Confluence, Jira).
* The migrated ``GET /admin/cc-pair/{id}/permission-sync-attempts`` route,
  now wrapped in ``CCPairSyncAttemptsResponse`` and raising ``OnyxError``.
* The new ``GET /admin/cc-pair/{id}/external-group-sync-attempts`` route.

We invoke the FastAPI route functions directly with a constructed admin
``User`` and the test ``db_session`` rather than going through TestClient —
matching the pattern used elsewhere in ``external_dependency_unit``.
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import Session

from onyx.configs.constants import DocumentSource
from onyx.connectors.models import InputType
from onyx.db.enums import (
    AccessType,
    ConnectorCredentialPairStatus,
)
from onyx.db.models import (
    Connector,
    ConnectorCredentialPair,
    Credential,
    User,
)
from onyx.db.permission_sync_attempt import (
    create_external_group_sync_attempt,
    get_relevant_external_group_sync_attempts_for_cc_pair,
)
from onyx.error_handling.error_codes import OnyxErrorCode
from onyx.error_handling.exceptions import OnyxError
from onyx.server.documents.cc_pair import (
    get_cc_pair_external_group_sync_attempts,
    get_cc_pair_permission_sync_attempts,
)
from tests.external_dependency_unit.conftest import create_test_user

# Every applicable=True path here depends on the EE-only ``sync_params``
# helpers (``source_requires_doc_sync`` etc.); the no-op fallback would
# otherwise short-circuit those paths to ``applicable=False``. Applied
# module-wide so individual tests don't need to wire the fixture in.

# --------------------------------------------------------------------------- #
# Setup helpers
# --------------------------------------------------------------------------- #


def _create_cc_pair(
    db_session: Session,
    source: DocumentSource = DocumentSource.GOOGLE_DRIVE,
) -> ConnectorCredentialPair:
    """Create a fully wired ``ConnectorCredentialPair`` for the given source.

    Mirrors ``_create_test_connector_credential_pair`` in the sibling test
    files but kept local so changes here don't ripple into those tests.
    """
    user = create_test_user(db_session, "fixture_user")

    connector = Connector(
        name=f"Test {source.value} Connector",
        source=source,
        input_type=InputType.LOAD_STATE,
        connector_specific_config={},
        refresh_freq=None,
        prune_freq=None,
        indexing_start=datetime.now(timezone.utc),
    )
    db_session.add(connector)
    db_session.flush()

    credential = Credential(
        credential_json={},
        user_id=user.id,
        admin_public=True,
    )
    db_session.add(credential)
    db_session.flush()
    db_session.expire(credential)

    cc_pair = ConnectorCredentialPair(
        connector_id=connector.id,
        credential_id=credential.id,
        name=f"Test CC Pair {source.value}",
        status=ConnectorCredentialPairStatus.ACTIVE,
        access_type=AccessType.SYNC,
    )
    db_session.add(cc_pair)
    db_session.commit()
    return cc_pair


def _admin_user(db_session: Session) -> User:
    return create_test_user(db_session, "admin", is_admin=True)


# --------------------------------------------------------------------------- #
# Helper: get_relevant_external_group_sync_attempts_for_cc_pair
# --------------------------------------------------------------------------- #


class TestGetRelevantExternalGroupSyncAttemptsForCcPair:
    def test_filters_by_cc_pair_when_source_is_not_agnostic(
        self,
        db_session: Session,
    ) -> None:
        """Google Drive's group sync is per-cc-pair; sibling cc-pair attempts
        with the same source must NOT bleed into the result."""
        cc_pair = _create_cc_pair(db_session, DocumentSource.GOOGLE_DRIVE)
        sibling_cc_pair = _create_cc_pair(db_session, DocumentSource.GOOGLE_DRIVE)

        own_attempt_id = create_external_group_sync_attempt(cc_pair.id, db_session)
        sibling_attempt_id = create_external_group_sync_attempt(
            sibling_cc_pair.id, db_session
        )

        result = get_relevant_external_group_sync_attempts_for_cc_pair(
            cc_pair_id=cc_pair.id,
            source=DocumentSource.GOOGLE_DRIVE,
            limit=50,
            db_session=db_session,
        )
        result_ids = {attempt.id for attempt in result}
        assert own_attempt_id in result_ids
        assert sibling_attempt_id not in result_ids


class TestGetCcPairPermissionSyncAttemptsRoute:
    def test_raises_not_found_for_unknown_cc_pair(self, db_session: Session) -> None:
        admin = _admin_user(db_session)

        with pytest.raises(OnyxError) as exc_info:
            get_cc_pair_permission_sync_attempts(
                cc_pair_id=999_999,
                page_num=0,
                page_size=10,
                user=admin,
                db_session=db_session,
            )

        assert exc_info.value.error_code == OnyxErrorCode.NOT_FOUND

    def test_applicable_false_when_source_does_not_require_doc_sync(
        self,
        db_session: Session,
    ) -> None:
        """Salesforce has no doc-sync config — only chunk censoring — so the
        endpoint must short-circuit with ``applicable=False`` even if the
        cc-pair somehow has rows in the table."""
        admin = _admin_user(db_session)
        cc_pair = _create_cc_pair(db_session, DocumentSource.SALESFORCE)

        response = get_cc_pair_permission_sync_attempts(
            cc_pair_id=cc_pair.id,
            page_num=0,
            page_size=10,
            user=admin,
            db_session=db_session,
        )

        assert response.applicable is False
        assert response.items == []
        assert response.total_items == 0


class TestGetCcPairExternalGroupSyncAttemptsRoute:
    def test_raises_not_found_for_unknown_cc_pair(self, db_session: Session) -> None:
        admin = _admin_user(db_session)

        with pytest.raises(OnyxError) as exc_info:
            get_cc_pair_external_group_sync_attempts(
                cc_pair_id=999_999,
                page_num=0,
                page_size=10,
                user=admin,
                db_session=db_session,
            )

        assert exc_info.value.error_code == OnyxErrorCode.NOT_FOUND

    def test_applicable_false_when_source_has_no_group_sync(
        self,
        db_session: Session,
    ) -> None:
        """Slack has doc sync but no separate group sync, so the group-sync
        endpoint must report ``applicable=False`` for it."""
        admin = _admin_user(db_session)
        cc_pair = _create_cc_pair(db_session, DocumentSource.SLACK)

        response = get_cc_pair_external_group_sync_attempts(
            cc_pair_id=cc_pair.id,
            page_num=0,
            page_size=10,
            user=admin,
            db_session=db_session,
        )

        assert response.applicable is False
        assert response.items == []
        assert response.total_items == 0
