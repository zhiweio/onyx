"""craft_loop.next_fire_at for the fire sweep

Revision ID: e3b8d1a6c4f9
Revises: d7a2c5e9f1b4
Create Date: 2026-09-30

Precomputed fire time for cron-triggered loops; the sweep task claims
rows on this column (FOR UPDATE SKIP LOCKED), mirroring
scheduled_task.next_run_at. NULL while not runnable or event-driven.
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "e3b8d1a6c4f9"
down_revision = "d7a2c5e9f1b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "craft_loop",
        sa.Column("next_fire_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_craft_loop_next_fire", "craft_loop", ["next_fire_at"])


def downgrade() -> None:
    op.drop_index("ix_craft_loop_next_fire", table_name="craft_loop")
    op.drop_column("craft_loop", "next_fire_at")
