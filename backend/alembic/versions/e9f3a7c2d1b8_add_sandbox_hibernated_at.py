"""add sandbox.hibernated_at

Revision ID: e9f3a7c2d1b8
Revises: d6e7f8a9b0c1
Create Date: 2026-09-16

Distinguishes a hibernated sandbox (container stopped, runtime kept for a
fast wake) from the legacy SLEEPING meaning (runtime destroyed). NULL keeps
the legacy behavior; the new column is only ever written together with a
RUNNING -> SLEEPING transition.
"""

import sqlalchemy as sa
from alembic import op

revision = "e9f3a7c2d1b8"
down_revision = "d6e7f8a9b0c1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sandbox",
        sa.Column("hibernated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("sandbox", "hibernated_at")
