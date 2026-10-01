"""china_im_binding table

Revision ID: f5c9e2b7a1d3
Revises: e3b8d1a6c4f9
Create Date: 2026-09-30

Platform IM identity ↔ Onyx user bindings recorded by the China bot
callbacks; push notifications (approval cards, loop-held outputs) DM
through the newest binding.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "f5c9e2b7a1d3"
down_revision = "e3b8d1a6c4f9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "china_im_binding",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("platform", sa.String(length=16), nullable=False),
        sa.Column("platform_user_id", sa.String(length=256), nullable=False),
        sa.Column("chat_id", sa.String(length=256), nullable=False),
        sa.Column(
            "display_name", sa.String(length=256), nullable=False, server_default=""
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
            "platform", "platform_user_id", name="uq_china_im_binding_platform_user"
        ),
    )
    op.create_index("ix_china_im_binding_user", "china_im_binding", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_china_im_binding_user", table_name="china_im_binding")
    op.drop_table("china_im_binding")
