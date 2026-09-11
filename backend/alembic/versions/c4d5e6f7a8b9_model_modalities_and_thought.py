"""per-model modalities, output tokens, thought, context usage

Revision ID: c4d5e6f7a8b9
Revises: b1c2d3e4f5a6
Create Date: 2026-09-12
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "c4d5e6f7a8b9"
down_revision = "b1c2d3e4f5a6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "model_configuration",
        sa.Column("max_output_tokens", sa.Integer(), nullable=True),
    )
    op.add_column(
        "model_configuration",
        sa.Column("input_modalities", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "model_configuration",
        sa.Column("output_modalities", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "chat_session",
        sa.Column("context_tokens_used", sa.Integer(), nullable=True),
    )
    op.add_column(
        "build_session",
        sa.Column("reasoning_effort", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("build_session", "reasoning_effort")
    op.drop_column("chat_session", "context_tokens_used")
    op.drop_column("model_configuration", "output_modalities")
    op.drop_column("model_configuration", "input_modalities")
    op.drop_column("model_configuration", "max_output_tokens")
