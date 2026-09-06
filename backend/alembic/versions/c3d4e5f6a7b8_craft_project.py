"""craft project tables and session project_id

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-08-30
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "craft_project",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("instructions", sa.Text(), nullable=True),
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
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_craft_project_user_created",
        "craft_project",
        ["user_id", sa.text("created_at DESC")],
    )

    op.create_table(
        "craft_project_file",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("path", sa.String(), nullable=False),
        sa.Column("file_id", sa.String(), nullable=False),
        sa.Column("mime_type", sa.String(), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("content_hash", sa.String(), nullable=True),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column(
            "produced_by_session_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("deleted", sa.Boolean(), nullable=False, server_default="false"),
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
        sa.ForeignKeyConstraint(
            ["project_id"], ["craft_project.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["produced_by_session_id"], ["build_session.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_craft_project_file_path",
        "craft_project_file",
        ["project_id", "path"],
        unique=True,
    )
    op.create_index(
        "ix_craft_project_file_project_id",
        "craft_project_file",
        ["project_id"],
    )

    op.add_column(
        "build_session",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_build_session_project_id",
        "build_session",
        "craft_project",
        ["project_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_build_session_project_id", "build_session", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_build_session_project_id", table_name="build_session")
    op.drop_constraint("fk_build_session_project_id", "build_session", type_="foreignkey")
    op.drop_column("build_session", "project_id")
    op.drop_index("ix_craft_project_file_project_id", table_name="craft_project_file")
    op.drop_index("uq_craft_project_file_path", table_name="craft_project_file")
    op.drop_table("craft_project_file")
    op.drop_index("ix_craft_project_user_created", table_name="craft_project")
    op.drop_table("craft_project")
