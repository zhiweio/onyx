"""Drop license table

Revision ID: d7f8a9b0c1e2
Revises: b9e5a3d8f2c7
Create Date: 2026-10-01

This build ships Community Edition only; the license machinery belonged to
the Enterprise Edition and is not present. The table has no readers or
writers in this codebase.
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "d7f8a9b0c1e2"
down_revision = "b9e5a3d8f2c7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("idx_license_singleton", table_name="license")
    op.drop_table("license")


def downgrade() -> None:
    # Best-effort inverse: the CE codebase never reads this table, so a plain
    # structural restore is enough.
    op.create_table(
        "license",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("license_data", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "idx_license_singleton",
        "license",
        [sa.text("(true)")],
        unique=True,
    )
