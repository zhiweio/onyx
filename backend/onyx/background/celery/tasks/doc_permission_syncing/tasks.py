"""Document permission sync runner.

Fills the CE celery slot the redis layer already references:
``onyx.background.celery.tasks.doc_permission_syncing.tasks`` (see
``RedisConnectorPermissionSync.update_db``). Three pieces:

- ``check_for_doc_permissions_sync`` — beat sweep; enqueues one generator
  per due connector credential pair whose connector implements
  ``SlimConnectorWithPermSync``.
- ``connector_permission_sync_generator_task`` — runs the connector's
  ``retrieve_all_slim_docs_perm_sync`` and pushes permission batches
  through ``perm_sync.update_db`` (which calls ``element_update_permissions``
  per document).
- ``element_update_permissions`` — plain function: persists one document's
  (or hierarchy node's) external access to Postgres and refreshes the
  indexed ACL for documents.
"""

import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from celery import Celery, Task, shared_task
from redis.lock import Lock as RedisLock
from sqlalchemy import select

from onyx.access.access import get_access_for_document
from onyx.access.models import (
    DocExternalAccess,
    DocumentAccess,
    ElementExternalAccess,
    NodeExternalAccess,
)
from onyx.background.celery.apps.app_base import task_logger
from onyx.background.celery.tasks.beat_schedule import BEAT_EXPIRES_DEFAULT
from onyx.background.celery.tasks.shared.RetryDocumentIndex import RetryDocumentIndex
from onyx.configs.app_configs import JOB_TIMEOUT
from onyx.configs.constants import (
    CELERY_GENERIC_BEAT_LOCK_TIMEOUT,
    DANSWER_REDIS_FUNCTION_LOCK_PREFIX,
    DocumentSource,
    OnyxCeleryPriority,
    OnyxCeleryQueues,
    OnyxCeleryTask,
    OnyxRedisLocks,
)
from onyx.connectors.factory import identify_connector_class, instantiate_connector
from onyx.connectors.interfaces import SlimConnectorWithPermSync
from onyx.connectors.models import SlimDocument
from onyx.db.connector_credential_pair import (
    fetch_indexable_standard_connector_credential_pair_ids,
    get_connector_credential_pair_from_id,
)
from onyx.db.document import fetch_chunk_count_for_document
from onyx.db.engine.sql_engine import (
    get_session_with_current_tenant,
    get_session_with_tenant,
)
from onyx.db.enums import ConnectorCredentialPairStatus
from onyx.db.models import ConnectorCredentialPair
from onyx.db.models import Document as DbDocument
from onyx.db.models import HierarchyNode as DbHierarchyNode
from onyx.db.permission_sync_attempt import (
    complete_doc_permission_sync_attempt,
    create_doc_permission_sync_attempt,
    mark_doc_permission_sync_attempt_failed,
    mark_doc_permission_sync_attempt_in_progress,
)
from onyx.db.search_settings import get_active_search_settings
from onyx.document_index.factory import get_all_document_indices
from onyx.document_index.interfaces_new import MetadataUpdateRequest
from onyx.httpx.httpx_pool import HttpxPool
from onyx.redis.redis_connector_doc_perm_sync import (
    RedisConnectorPermissionSync,
)
from onyx.redis.redis_pool import get_redis_client
from onyx.utils.logger import setup_logger

logger = setup_logger()

# Permission sync runs once per day per connector, mirroring the upstream
# cadence (hourly sweep, 24h due interval).
DOC_PERMISSIONS_SYNC_INTERVAL_SECONDS = 24 * 60 * 60

# Number of documents per update_db call.
DOC_PERMISSIONS_SYNC_BATCH_SIZE = 100


def _connector_supports_perm_sync(cc_pair: ConnectorCredentialPair) -> bool:
    try:
        connector_class = identify_connector_class(cc_pair.connector.source)
    except Exception:
        task_logger.warning(
            "Skipping perm sync enqueue for unknown source=%s input_type=%s",
            cc_pair.connector.source,
            cc_pair.connector.input_type,
        )
        return False
    return issubclass(connector_class, SlimConnectorWithPermSync)


def _is_perm_sync_due(cc_pair: ConnectorCredentialPair) -> bool:
    if cc_pair.status != ConnectorCredentialPairStatus.ACTIVE:
        return False
    # Only sync permissions for connectors that have indexed at least once,
    # otherwise there are no documents to update.
    if not cc_pair.last_successful_index_time:
        return False
    last_sync = cc_pair.last_time_perm_sync
    if last_sync is None:
        return True
    return datetime.now(timezone.utc) >= last_sync + timedelta(
        seconds=DOC_PERMISSIONS_SYNC_INTERVAL_SECONDS
    )


def _try_creating_perm_sync_task(
    celery_app: Celery,
    cc_pair: ConnectorCredentialPair,
    tenant_id: str,
) -> str | None:
    LOCK_TIMEOUT = 30
    redis_client = get_redis_client(tenant_id=tenant_id)
    lock: RedisLock = redis_client.lock(
        DANSWER_REDIS_FUNCTION_LOCK_PREFIX + f"perm_sync_enqueue_{cc_pair.id}",
        timeout=LOCK_TIMEOUT,
    )
    if not lock.acquire(blocking_timeout=LOCK_TIMEOUT / 2):
        return None
    try:
        custom_task_id = f"perm_sync_{cc_pair.id}_{uuid4()}"
        result = celery_app.send_task(
            OnyxCeleryTask.CONNECTOR_PERMISSION_SYNC_GENERATOR_TASK,
            kwargs=dict(cc_pair_id=cc_pair.id, tenant_id=tenant_id),
            queue=OnyxCeleryQueues.CONNECTOR_DOC_PERMISSIONS_SYNC,
            task_id=custom_task_id,
            priority=OnyxCeleryPriority.LOW,
            expires=BEAT_EXPIRES_DEFAULT,
        )
        if not result:
            raise RuntimeError("send_task for perm sync generator failed.")
        task_logger.info(
            "Created perm sync task: cc_pair=%s celery_task_id=%s",
            cc_pair.id,
            custom_task_id,
        )
        return custom_task_id
    except Exception:
        task_logger.exception("Failed to create perm sync task: cc_pair=%s", cc_pair.id)
        return None
    finally:
        if lock.owned():
            lock.release()


@shared_task(  # ty: ignore[invalid-argument-type]
    name=OnyxCeleryTask.CHECK_FOR_DOC_PERMISSIONS_SYNC,
    soft_time_limit=300,
    bind=True,
)
def check_for_doc_permissions_sync(self: Task, *, tenant_id: str) -> int | None:
    """Beat sweep: enqueue a permission sync generator for every due cc pair."""
    time_start = time.monotonic()
    tasks_created = 0
    redis_client = get_redis_client()

    lock_beat: RedisLock = redis_client.lock(
        OnyxRedisLocks.CHECK_CONNECTOR_DOC_PERMISSIONS_SYNC_BEAT_LOCK,
        timeout=CELERY_GENERIC_BEAT_LOCK_TIMEOUT,
    )
    if not lock_beat.acquire(blocking=False):
        return None

    try:
        with get_session_with_current_tenant() as db_session:
            cc_pair_ids = fetch_indexable_standard_connector_credential_pair_ids(
                db_session=db_session,
                active_cc_pairs_only=True,
            )
            for cc_pair_id in cc_pair_ids:
                lock_beat.reacquire()
                cc_pair = get_connector_credential_pair_from_id(
                    db_session=db_session,
                    cc_pair_id=cc_pair_id,
                )
                if not cc_pair or not _connector_supports_perm_sync(cc_pair):
                    continue
                if not _is_perm_sync_due(cc_pair):
                    continue
                task_id = _try_creating_perm_sync_task(
                    celery_app=self.app,
                    cc_pair=cc_pair,
                    tenant_id=tenant_id,
                )
                if task_id:
                    tasks_created += 1
    except Exception:
        task_logger.exception("check_for_doc_permissions_sync - Unexpected error")
    finally:
        if lock_beat.owned():
            lock_beat.release()

    task_logger.info(
        "check_for_doc_permissions_sync finished: tasks_created=%s elapsed=%.2fs",
        tasks_created,
        time.monotonic() - time_start,
    )
    return tasks_created


@shared_task(  # ty: ignore[invalid-argument-type]
    name=OnyxCeleryTask.CONNECTOR_PERMISSION_SYNC_GENERATOR_TASK,
    soft_time_limit=JOB_TIMEOUT,
    bind=True,
)
def connector_permission_sync_generator_task(
    self: Task,  # noqa: ARG001
    *,
    cc_pair_id: int,
    tenant_id: str,
) -> None:
    """Run one full permission sync for a cc pair: slim docs → external
    access → DB + index, recorded as a DocPermissionSyncAttempt."""
    task_logger.info(
        "perm sync generator starting: cc_pair=%s tenant=%s", cc_pair_id, tenant_id
    )

    redis_client = get_redis_client(tenant_id=tenant_id)
    perm_sync = RedisConnectorPermissionSync(
        tenant_id=tenant_id, id=cc_pair_id, redis=redis_client
    )

    lock: RedisLock = redis_client.lock(
        OnyxRedisLocks.CONNECTOR_DOC_PERMISSIONS_SYNC_LOCK_PREFIX + f"_{cc_pair_id}",
        timeout=CELERY_GENERIC_BEAT_LOCK_TIMEOUT,
    )
    if not lock.acquire(blocking=False):
        task_logger.info(
            "perm sync already running for cc_pair=%s, skipping", cc_pair_id
        )
        return

    attempt_id: int | None = None
    try:
        with get_session_with_tenant(tenant_id=tenant_id) as db_session:
            cc_pair = get_connector_credential_pair_from_id(
                db_session=db_session,
                cc_pair_id=cc_pair_id,
            )
            if (
                cc_pair is None
                or cc_pair.status != ConnectorCredentialPairStatus.ACTIVE
            ):
                task_logger.info(
                    "perm sync cc_pair=%s no longer active, skipping", cc_pair_id
                )
                return

            attempt_id = create_doc_permission_sync_attempt(cc_pair_id, db_session)
            mark_doc_permission_sync_attempt_in_progress(attempt_id, db_session)

            # Stamp the schedule marker at start: a crashed run won't be
            # re-enqueued until the next interval, which is the same
            # behavior as the indexing sweep.
            start = (
                cc_pair.last_time_perm_sync.timestamp()
                if cc_pair.last_time_perm_sync
                else 0
            )
            end = datetime.now(timezone.utc).timestamp()
            cc_pair.last_time_perm_sync = datetime.now(timezone.utc)
            db_session.commit()

            runnable_connector = instantiate_connector(
                db_session=db_session,
                source=cc_pair.connector.source,
                input_type=cc_pair.connector.input_type,
                connector_specific_config=cc_pair.connector.connector_specific_config,
                credential=cc_pair.credential,
            )
            source_string = cc_pair.connector.source.value
            connector_id = cc_pair.connector_id
            credential_id = cc_pair.credential_id

        if not isinstance(runnable_connector, SlimConnectorWithPermSync):
            task_logger.info(
                "perm sync cc_pair=%s: connector lacks SlimConnectorWithPermSync, "
                "marking canceled",
                cc_pair_id,
            )
            assert attempt_id is not None
            with get_session_with_tenant(tenant_id=tenant_id) as db_session:
                complete_doc_permission_sync_attempt(
                    db_session,
                    attempt_id,
                    total_docs_synced=0,
                    docs_with_permission_errors=0,
                )
            return

        total_synced = 0
        total_errors = 0
        batch: list[ElementExternalAccess] = []

        def _flush() -> tuple[int, int]:
            if not batch:
                return 0, 0
            result = perm_sync.update_db(
                lock,
                batch,
                source_string,
                connector_id,
                credential_id,
                task_logger=task_logger,
            )
            count = len(batch)
            batch.clear()
            return count, result.num_errors

        for slim_docs in runnable_connector.retrieve_all_slim_docs_perm_sync(
            start=start, end=end
        ):
            lock.reacquire()
            for slim in slim_docs:
                if not isinstance(slim, SlimDocument):
                    continue  # hierarchy nodes carry their own sync path
                if slim.external_access is None:
                    continue
                batch.append(
                    DocExternalAccess(
                        external_access=slim.external_access,
                        doc_id=slim.id,
                    )
                )
                if len(batch) >= DOC_PERMISSIONS_SYNC_BATCH_SIZE:
                    count, errors = _flush()
                    total_synced += count
                    total_errors += errors

        count, errors = _flush()
        total_synced += count
        total_errors += errors

        assert attempt_id is not None
        with get_session_with_tenant(tenant_id=tenant_id) as db_session:
            complete_doc_permission_sync_attempt(
                db_session,
                attempt_id,
                total_docs_synced=total_synced,
                docs_with_permission_errors=total_errors,
            )
        task_logger.info(
            "perm sync cc_pair=%s complete: synced=%s errors=%s",
            cc_pair_id,
            total_synced,
            total_errors,
        )
    except Exception as e:
        task_logger.exception("perm sync generator failed: cc_pair=%s", cc_pair_id)
        if attempt_id is not None:
            try:
                with get_session_with_tenant(tenant_id=tenant_id) as db_session:
                    mark_doc_permission_sync_attempt_failed(
                        attempt_id, db_session, str(e)
                    )
            except Exception:
                task_logger.exception(
                    "Failed to mark perm sync attempt failed: cc_pair=%s", cc_pair_id
                )
    finally:
        if lock.owned():
            lock.release()


def element_update_permissions(
    tenant_id: str,
    permissions: ElementExternalAccess,
    source_string: str,
    connector_id: int,
    credential_id: int,
) -> None:
    """Persist one element's external access and refresh the indexed ACL.

    Called inline (not as a celery task) by
    ``RedisConnectorPermissionSync.update_db`` — permissions can be too
    large to send over the wire.
    """
    del connector_id, credential_id  # audit columns already live on the attempt
    if isinstance(permissions, DocExternalAccess):
        _update_document_permissions(tenant_id, permissions)
    elif isinstance(permissions, NodeExternalAccess):
        _update_hierarchy_node_permissions(tenant_id, permissions, source_string)


def _update_document_permissions(
    tenant_id: str, permissions: DocExternalAccess
) -> None:
    access = permissions.external_access
    # Phase 1: Postgres — external access columns, then the combined ACL.
    with get_session_with_tenant(tenant_id=tenant_id) as db_session:
        doc = db_session.scalar(
            select(DbDocument).where(DbDocument.id == permissions.doc_id)
        )
        if doc is None:
            # Never indexed (or since deleted): nothing to update.
            return
        doc.external_user_emails = list(access.external_user_emails)
        doc.external_user_group_ids = list(access.external_user_group_ids)
        doc.is_public = access.is_public
        db_session.commit()

        doc_access = get_access_for_document(permissions.doc_id, db_session)
        chunk_count = fetch_chunk_count_for_document(permissions.doc_id, db_session)
        active_search_settings = get_active_search_settings(db_session)

    # Phase 2: index I/O — no DB connection held.
    update_request = _build_metadata_update(permissions.doc_id, doc_access, chunk_count)
    document_indices = get_all_document_indices(
        active_search_settings.primary,
        active_search_settings.secondary,
        httpx_client=HttpxPool.get("vespa"),
    )
    for document_index in document_indices:
        retry_index = RetryDocumentIndex(document_index)
        retry_index.update([update_request])


def _build_metadata_update(
    document_id: str, doc_access: DocumentAccess, chunk_count: int | None
) -> MetadataUpdateRequest:
    return MetadataUpdateRequest(
        document_ids=[document_id],
        doc_id_to_chunk_cnt={
            document_id: chunk_count if chunk_count is not None else -1
        },
        access=doc_access,
    )


def _update_hierarchy_node_permissions(
    tenant_id: str, permissions: NodeExternalAccess, source_string: str
) -> None:
    """Hierarchy node ACLs are DB/UI-only; no index copy exists to refresh."""
    access = permissions.external_access
    with get_session_with_tenant(tenant_id=tenant_id) as db_session:
        node = db_session.scalar(
            select(DbHierarchyNode).where(
                DbHierarchyNode.raw_node_id == permissions.raw_node_id,
                DbHierarchyNode.source == DocumentSource(source_string),
            )
        )
        if node is None:
            return
        node.external_user_emails = list(access.external_user_emails)
        node.external_user_group_ids = list(access.external_user_group_ids)
        node.is_public = access.is_public
        db_session.commit()
