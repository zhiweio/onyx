"""craft workspace catalog: pending hydrate and team projects

Revision ID: a8b9c0d1e2f3
Revises: f2a3b4c5d6e7
Create Date: 2026-09-09
"""

from alembic import op
import sqlalchemy as sa

revision = "a8b9c0d1e2f3"
down_revision = "f2a3b4c5d6e7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "artifact",
        sa.Column(
            "pending_hydrate",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "craft_project",
        sa.Column("user_group_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_craft_project_user_group_id",
        "craft_project",
        "user_group",
        ["user_group_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_craft_project_user_group_id",
        "craft_project",
        ["user_group_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_craft_project_user_group_id", table_name="craft_project")
    op.drop_constraint(
        "fk_craft_project_user_group_id", "craft_project", type_="foreignkey"
    )
    op.drop_column("craft_project", "user_group_id")
    op.drop_column("artifact", "pending_hydrate")
