"""word report template assets

Adds the DOCX template kind: a Word asset in the file store plus the
``{{placeholder}}`` contract extracted from it, on both the runtime table and
the catalog.

Existing rows are markdown, which the ``MARKDOWN`` server default already
states, so no backfill is needed.

Revision ID: d8e9f0a1b2c3
Revises: c7d8e9f0a1b2
Create Date: 2026-09-05
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "d8e9f0a1b2c3"
down_revision = "c7d8e9f0a1b2"
branch_labels = None
depends_on = None

_TABLES = ("report_template", "system_report_template")


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(
            table,
            sa.Column(
                "kind",
                sa.String(length=32),
                nullable=False,
                server_default="MARKDOWN",
            ),
        )
        op.add_column(table, sa.Column("asset_file_id", sa.String(), nullable=True))
        op.add_column(
            table, sa.Column("asset_sha256", sa.String(length=64), nullable=True)
        )
        op.add_column(
            table, sa.Column("asset_filename", sa.String(length=255), nullable=True)
        )
        op.add_column(
            table,
            sa.Column(
                "placeholders",
                postgresql.JSONB(),
                nullable=False,
                server_default=sa.text("'[]'"),
            ),
        )


def downgrade() -> None:
    for table in _TABLES:
        op.drop_column(table, "placeholders")
        op.drop_column(table, "asset_filename")
        op.drop_column(table, "asset_sha256")
        op.drop_column(table, "asset_file_id")
        op.drop_column(table, "kind")
