"""env vars + scheduled-task env-var grants

Introduces Craft environment variables / secrets (``env_var``): user- or
project-scoped rows with encrypted values. Scheduled tasks gain an optional
``project_id`` (belonging to a project is what makes that project's vars
grantable) and the ``scheduled_task_env_var`` grant table — only explicitly
granted rows are substituted into a run's prompt.

Revision ID: a7c3e9f1b2d4
Revises: e9f3a7c2d1b8
Create Date: 2026-09-23

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "a7c3e9f1b2d4"
down_revision = "e9f3a7c2d1b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "env_var",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column(
            "is_secret", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("scope", sa.String(), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("value", sa.LargeBinary(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(scope = 'USER' AND project_id IS NULL) "
            "OR (scope = 'PROJECT' AND project_id IS NOT NULL)",
            name="ck_env_var_scope_project",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["craft_project.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_env_var_user_name",
        "env_var",
        ["user_id", "name"],
        unique=True,
        postgresql_where=sa.text("project_id IS NULL"),
    )
    op.create_index(
        "uq_env_var_project_name",
        "env_var",
        ["project_id", "name"],
        unique=True,
        postgresql_where=sa.text("project_id IS NOT NULL"),
    )
    op.create_index(
        "ix_env_var_user_updated",
        "env_var",
        ["user_id", sa.text("updated_at DESC")],
    )

    op.add_column(
        "scheduled_task",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_scheduled_task_project_id",
        "scheduled_task",
        "craft_project",
        ["project_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "scheduled_task_env_var",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("scheduled_task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("env_var_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["scheduled_task_id"], ["scheduled_task.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["env_var_id"], ["env_var.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "scheduled_task_id",
            "env_var_id",
            name="uq_scheduled_task_env_var",
        ),
    )


def downgrade() -> None:
    op.drop_table("scheduled_task_env_var")
    op.drop_constraint(
        "fk_scheduled_task_project_id", "scheduled_task", type_="foreignkey"
    )
    op.drop_column("scheduled_task", "project_id")
    op.drop_index("ix_env_var_user_updated", table_name="env_var")
    op.drop_index("uq_env_var_project_name", table_name="env_var")
    op.drop_index("uq_env_var_user_name", table_name="env_var")
    op.drop_table("env_var")
