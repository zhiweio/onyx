"""Craft tape archive batch ledger for the PG-to-Iceberg pipeline.

One ``craft_tape_archive_batch`` row per archival pass: written ``pending``
before the lake append, flipped to ``done`` after the atomic snapshot
commit. The max ``max_source_id`` among done batches is the high-water
mark bounding Postgres pruning and the cold-read split.

Revision ID: a3c7e9f5b2d4
Revises: a7c9d2e5b8f4
Create Date: 2026-10-05
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "a3c7e9f5b2d4"
down_revision = "a7c9d2e5b8f4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "craft_tape_archive_batch",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("max_source_id", sa.BigInteger(), nullable=False),
        sa.Column("event_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_craft_tape_archive_batch_status",
        "craft_tape_archive_batch",
        ["status", "max_source_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_craft_tape_archive_batch_status", table_name="craft_tape_archive_batch"
    )
    op.drop_table("craft_tape_archive_batch")
