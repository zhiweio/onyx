"""action policy versioning + scheduled task graduation

Revision ID: d1f6a8b2c4e7
Revises: c9e4b7a1d3f5
Create Date: 2026-09-26

The QM ship-gate invariant: grants are bound to a policy version and any
policy edit reverts them to ASK. ``gated_app.policy_version`` is the counter
that bumps on every policy edit; grants (action_approval rows, scheduled-task
pre-approvals) stamp the version they were made under and only cover requests
while it matches. The graduation table tracks consecutive supervised approvals
per (task, target) toward an automatic pre-approval.
"""

import sqlalchemy as sa
from alembic import op

revision = "d1f6a8b2c4e7"
down_revision = "c9e4b7a1d3f5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "gated_app",
        sa.Column(
            "policy_version",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
    )
    op.add_column(
        "action_approval",
        sa.Column("policy_version", sa.Integer(), nullable=True),
    )
    # Grants made before versioning existed were made under the policy as it
    # stands now (version 1) — stamp them so they keep covering.
    op.execute(
        "UPDATE action_approval a SET policy_version = g.policy_version "
        "FROM gated_app g WHERE a.gated_app_id = g.id"
    )
    op.add_column(
        "scheduled_task_pre_approved_app",
        sa.Column(
            "policy_version",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
    )
    op.create_table(
        "scheduled_task_graduation",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "scheduled_task_id",
            sa.UUID(),
            sa.ForeignKey("scheduled_task.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "gated_app_id",
            sa.Integer(),
            sa.ForeignKey("gated_app.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "consecutive_passes", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "policy_version", sa.Integer(), nullable=False, server_default=sa.text("1")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "scheduled_task_id",
            "gated_app_id",
            name="uq_scheduled_task_graduation",
        ),
    )


def downgrade() -> None:
    op.drop_table("scheduled_task_graduation")
    op.drop_column("scheduled_task_pre_approved_app", "policy_version")
    op.drop_column("action_approval", "policy_version")
    op.drop_column("gated_app", "policy_version")
