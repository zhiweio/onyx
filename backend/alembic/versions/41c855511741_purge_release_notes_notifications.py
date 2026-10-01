"""Purge release-notes notifications

Revision ID: c3d4e5f6a7b8
Revises: d7f8a9b0c1e2
Create Date: 2026-10-01

This deployment is an internal fork that does not track upstream Onyx
releases, and ENABLE_RELEASE_NOTES_NOTIFICATIONS now defaults to off.
Delete the already-materialized upstream release announcements so no user
keeps seeing "Onyx vX.Y is available" toasts.
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "41c855511741"
down_revision = "d7f8a9b0c1e2"
branch_labels = None
depends_on = None

# Enum values are stored as the enum member names (native_enum=False).
RELEASE_NOTES = "RELEASE_NOTES"


def upgrade() -> None:
    op.execute(
        sa.text("DELETE FROM notification WHERE notif_type = :notif_type").bindparams(
            notif_type=RELEASE_NOTES
        )
    )


def downgrade() -> None:
    # The rows were generated from the public upstream changelog; no restore.
    pass
