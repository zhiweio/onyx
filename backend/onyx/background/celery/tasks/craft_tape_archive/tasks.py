"""Craft tape archival and retention tasks (PG hot window ↔ Iceberg lake)."""

from datetime import datetime, timedelta, timezone

from celery import shared_task

from onyx.configs.app_configs import (
    CRAFT_TAPE_ARCHIVE_ENABLED,
    CRAFT_TAPE_HOT_RETENTION_DAYS,
    CRAFT_TAPE_ICEBERG_RETENTION_DAYS,
)
from onyx.configs.constants import OnyxCeleryTask
from onyx.utils.logger import setup_logger

logger = setup_logger()


@shared_task(
    name=OnyxCeleryTask.CRAFT_TAPE_ARCHIVE_TO_ICEBERG,
    soft_time_limit=600,
    ignore_result=True,
)
def craft_tape_archive_to_iceberg(*, tenant_id: str) -> None:  # noqa: ARG001
    """Move closed-turn tape batches from Postgres into the Iceberg lake.

    The pass is high-water driven and idempotent: rows archived in a done
    batch are never re-fetched, and a turn archives only after its
    turn/end fact exists.
    """
    if not CRAFT_TAPE_ARCHIVE_ENABLED:
        return
    # Imported lazily: the lake stack pulls in pyiceberg/pyarrow.
    from onyx.server.features.build.tape_archive.archival import run_archive_pass

    run_archive_pass()


def prune_craft_tape_hot_window() -> int:
    """Retention shared by the beat task: PG hot window + lake expiry.

    Postgres only ever drops rows the lake already holds (bounded by the
    done-batch high-water mark) and only past the hot window; the lake
    expires separately on its own retention. Returns PG rows removed.
    """
    from onyx.db.craft_tape import prune_tape_before, tape_retention_cutoff
    from onyx.db.craft_tape_archive import archived_high_water
    from onyx.db.engine.sql_engine import get_session_with_current_tenant
    from onyx.server.features.build.configs import CRAFT_TAPE_RETENTION_DAYS

    if not CRAFT_TAPE_ARCHIVE_ENABLED:
        # Unarchived tape keeps the historical single-tier retention.
        with get_session_with_current_tenant() as db_session:
            removed = prune_tape_before(
                db_session, tape_retention_cutoff(CRAFT_TAPE_RETENTION_DAYS)
            )
            db_session.commit()
        return removed

    removed = 0
    with get_session_with_current_tenant() as db_session:
        high_water = archived_high_water(db_session)
        if CRAFT_TAPE_HOT_RETENTION_DAYS > 0:
            cutoff = datetime.now(tz=timezone.utc) - timedelta(
                days=CRAFT_TAPE_HOT_RETENTION_DAYS
            )
            removed = prune_tape_before(db_session, cutoff, max_id=high_water)
            db_session.commit()

    if CRAFT_TAPE_ICEBERG_RETENTION_DAYS > 0:
        from onyx.server.features.build.tape_archive.lake.io import expire_before

        lake_cutoff = datetime.now(tz=timezone.utc) - timedelta(
            days=CRAFT_TAPE_ICEBERG_RETENTION_DAYS
        )
        expired = expire_before(lake_cutoff)
        if expired:
            logger.info(
                "Craft tape lake expired %s turns older than %s",
                expired,
                lake_cutoff,
            )
    return removed
