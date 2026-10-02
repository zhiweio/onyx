"""Report template contract and theme

Revision ID: b7a1c9d2e3f4
Revises: 41c855511741
Create Date: 2026-10-03

Contract-style templates carry a structured content contract and a render
theme next to the markdown guide. Both columns are optional: an empty object
means the legacy layout-reference behaviour.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "b7a1c9d2e3f4"
down_revision = "41c855511741"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("report_template", "system_report_template"):
        op.add_column(
            table,
            sa.Column(
                "contract",
                postgresql.JSONB(),
                nullable=True,
                server_default=sa.text("'{}'::jsonb"),
            ),
        )
        op.add_column(
            table,
            sa.Column(
                "theme",
                postgresql.JSONB(),
                nullable=True,
                server_default=sa.text("'{}'::jsonb"),
            ),
        )


def downgrade() -> None:
    for table in ("report_template", "system_report_template"):
        op.drop_column(table, "theme")
        op.drop_column(table, "contract")
