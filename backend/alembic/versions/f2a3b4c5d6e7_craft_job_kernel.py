"""craft job kernel channels, checkpoints, and journal

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-09-06
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "f2a3b4c5d6e7"
down_revision = "e1f2a3b4c5d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "craft_job",
        sa.Column(
            "state",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column("craft_job", sa.Column("lease_owner", sa.String(length=64), nullable=True))
    op.add_column(
        "craft_job",
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("craft_job", sa.Column("drain_reason", sa.Text(), nullable=True))

    op.add_column(
        "craft_job_specialist",
        sa.Column("node_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "craft_job_specialist",
        sa.Column("checkpoint_ns", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "craft_job_specialist",
        sa.Column("input_digest", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "craft_job_specialist",
        sa.Column(
            "output_artifact_ids",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )

    op.create_table(
        "craft_job_checkpoint",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ns", sa.String(length=128), nullable=False),
        sa.Column("step", sa.Integer(), nullable=False),
        sa.Column("writes", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["job_id"], ["craft_job.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_craft_job_checkpoint_job_step",
        "craft_job_checkpoint",
        ["job_id", "ns", "step"],
    )

    op.create_table(
        "craft_job_event",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["job_id"], ["craft_job.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_craft_job_event_job_created",
        "craft_job_event",
        ["job_id", "created_at"],
    )

    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            DELETE FROM scenario__skill
            WHERE skill_id IN (
                SELECT id FROM skill WHERE built_in_skill_id = 'long-job-protocol'
            )
            """
        )
    )
    conn.execute(
        sa.text(
            """
            UPDATE system_skill
            SET publish_status = 'ARCHIVED'
            WHERE slug = 'long-job-protocol'
            """
        )
    )


def downgrade() -> None:
    op.drop_index("ix_craft_job_event_job_created", table_name="craft_job_event")
    op.drop_table("craft_job_event")
    op.drop_index("ix_craft_job_checkpoint_job_step", table_name="craft_job_checkpoint")
    op.drop_table("craft_job_checkpoint")
    op.drop_column("craft_job_specialist", "output_artifact_ids")
    op.drop_column("craft_job_specialist", "input_digest")
    op.drop_column("craft_job_specialist", "checkpoint_ns")
    op.drop_column("craft_job_specialist", "node_id")
    op.drop_column("craft_job", "drain_reason")
    op.drop_column("craft_job", "lease_expires_at")
    op.drop_column("craft_job", "lease_owner")
    op.drop_column("craft_job", "state")
