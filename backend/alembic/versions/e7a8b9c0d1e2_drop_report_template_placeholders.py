"""drop report template placeholder schema

The agent uses the markdown body and optional Word file as references.
A stored placeholder contract is unused.

Revision ID: e7a8b9c0d1e2
Revises: d6e7f8a9b0c1
Create Date: 2026-09-12
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "e7a8b9c0d1e2"
down_revision = "c4d5e6f7a8b9"
branch_labels = None
depends_on = None

_TABLES = ("report_template", "system_report_template")


def upgrade() -> None:
    for table in _TABLES:
        op.drop_column(table, "placeholders")


def downgrade() -> None:
    for table in _TABLES:
        op.add_column(
            table,
            sa.Column(
                "placeholders",
                postgresql.JSONB(),
                nullable=False,
                server_default=sa.text("'[]'"),
            ),
        )
