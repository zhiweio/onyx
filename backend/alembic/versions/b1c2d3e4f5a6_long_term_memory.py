"""user-isolated long-term memory with pgvector

Revision ID: b1c2d3e4f5a6
Revises: a8b9c0d1e2f3
Create Date: 2026-09-09
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "b1c2d3e4f5a6"
down_revision = "a8b9c0d1e2f3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.add_column(
        "user",
        sa.Column(
            "craft_use_long_term_memory",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "user",
        sa.Column(
            "chat_memory_mode",
            sa.String(),
            nullable=False,
            server_default="short_term",
        ),
    )
    op.create_check_constraint(
        "ck_user_chat_memory_mode",
        "user",
        "chat_memory_mode IN ('short_term', 'long_term')",
    )

    op.create_table(
        "long_term_memory",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("kind", sa.String(), nullable=False, server_default="semantic"),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(), nullable=False, server_default="extract"),
        sa.Column("source_surface", sa.String(), nullable=False),
        sa.Column("source_session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("importance", sa.Float(), nullable=True),
        sa.Column("embedding_model", sa.String(), nullable=True),
        sa.Column("embedding_dims", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_used_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["project_id"], ["craft_project.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute("ALTER TABLE long_term_memory ADD COLUMN embedding vector")
    op.create_index(
        "ix_long_term_memory_user_deleted",
        "long_term_memory",
        ["user_id", "deleted_at"],
    )
    op.create_index(
        "ix_long_term_memory_user_hash",
        "long_term_memory",
        ["user_id", "content_hash"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_long_term_memory_user_hash", table_name="long_term_memory")
    op.drop_index("ix_long_term_memory_user_deleted", table_name="long_term_memory")
    op.drop_table("long_term_memory")
    op.drop_constraint("ck_user_chat_memory_mode", "user", type_="check")
    op.drop_column("user", "chat_memory_mode")
    op.drop_column("user", "craft_use_long_term_memory")
