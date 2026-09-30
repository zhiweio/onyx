"""add scheduled_task.reviewer_mode

Revision ID: b6f0d3a8e2c5
Revises: a2c7e9f4b5d3
Create Date: 2026-09-27

Auto-review guardian configuration: `user` (default, approvals always go to
the human), `auto_review_shadow` (the guardian records its verdict for
evaluation but never decides), `auto_review` (the guardian approves/rejects
ASK-gated actions on the task's runs, with guardrails).
"""

import sqlalchemy as sa
from alembic import op

revision = "b6f0d3a8e2c5"
down_revision = "a2c7e9f4b5d3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "scheduled_task",
        sa.Column(
            "reviewer_mode",
            sa.String(32),
            nullable=False,
            server_default="user",
        ),
    )


def downgrade() -> None:
    op.drop_column("scheduled_task", "reviewer_mode")
