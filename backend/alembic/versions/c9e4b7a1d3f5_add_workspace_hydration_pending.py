"""add build_session.workspace_hydration_pending

Revision ID: c9e4b7a1d3f5
Revises: a7c3e9f1b2d4
Create Date: 2026-09-26

Durable "restore in progress" marker for a session workspace (the QM
hydrationPending pattern): set before a workspace restore or fresh setup
starts, cleared after it completes. A crash mid-restore leaves it set, so no
later turn mistakes a half-written workspace for a restored one; the next
ensure_session_ready discards the partial workspace and rebuilds.
"""

import sqlalchemy as sa
from alembic import op

revision = "c9e4b7a1d3f5"
down_revision = "a7c3e9f1b2d4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "build_session",
        sa.Column(
            "workspace_hydration_pending",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("build_session", "workspace_hydration_pending")
