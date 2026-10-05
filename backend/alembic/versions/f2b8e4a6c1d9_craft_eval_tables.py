"""Craft golden-set eval runs and per-case results.

One ``craft_eval_run`` executes the built-in eval cases headlessly and
records the aggregated score plus a model snapshot; per-case findings
(deterministic + fresh-context judge) land in ``craft_eval_case_result``
with a deep link to the eval build session for tape replay.

Revision ID: f2b8e4a6c1d9
Revises: d7f4a2c9e1b5
Create Date: 2026-10-05
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "f2b8e4a6c1d9"
down_revision = "d7f4a2c9e1b5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "craft_eval_run",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "trigger",
            sa.String(length=32),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("case_count", sa.Integer(), nullable=False),
        sa.Column("passed_count", sa.Integer(), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("model_provider", sa.String(length=128), nullable=True),
        sa.Column("model_name", sa.String(length=128), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("summary", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["user.id"], ondelete="SET NULL"
        ),
    )
    op.create_index(
        "ix_craft_eval_run_created",
        "craft_eval_run",
        [sa.text("created_at DESC")],
    )

    op.create_table(
        "craft_eval_case_result",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("case_slug", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column(
            "deterministic_findings",
            postgresql.JSONB(),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "judge_verdict",
            postgresql.JSONB(),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["run_id"], ["craft_eval_run.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["session_id"], ["build_session.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint("run_id", "case_slug"),
    )
    op.create_index("ix_craft_eval_case_slug", "craft_eval_case_result", ["case_slug"])


def downgrade() -> None:
    op.drop_index("ix_craft_eval_case_slug", table_name="craft_eval_case_result")
    op.drop_table("craft_eval_case_result")
    op.drop_index("ix_craft_eval_run_created", table_name="craft_eval_run")
    op.drop_table("craft_eval_run")
