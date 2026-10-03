"""Drop agent_model_overlay

Revision ID: c3f8a9d1e5b2
Revises: b7a1c9d2e3f4
Create Date: 2026-10-04

The agent model registry now derives from the gateway catalog (the
admin-configured LLM providers), so the overlay table has no consumer.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "c3f8a9d1e5b2"
down_revision = "b7a1c9d2e3f4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_agent_model_overlay_enabled", table_name="agent_model_overlay")
    op.drop_table("agent_model_overlay")


def downgrade() -> None:
    op.create_table(
        "agent_model_overlay",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("template_model_id", sa.String(length=128), nullable=False),
        sa.Column("model_id", sa.String(length=128), nullable=False),
        sa.Column("context_window", sa.Integer(), nullable=True),
        sa.Column("max_output_tokens", sa.Integer(), nullable=True),
        sa.Column("base_url", sa.String(length=512), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("fingerprint", sa.String(length=128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verify_error", sa.Text(), nullable=True),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("model_id", name="uq_agent_model_overlay_model_id"),
    )
    op.create_index(
        "ix_agent_model_overlay_enabled", "agent_model_overlay", ["enabled"]
    )
