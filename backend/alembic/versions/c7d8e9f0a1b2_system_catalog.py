"""system catalog tables for the craft galleries

Creates the admin-owned catalog (``system_skill`` / ``system_scenario`` /
``system_report_template``) and the pointers that link a runtime row back to the
catalog entry it was projected or forked from.

Content is not seeded here. ``sync_builtin_system_catalog`` reconciles the
shipped manifest at startup, which keeps this migration free of ORM imports and
lets shipped content change without a new migration.

Revision ID: c7d8e9f0a1b2
Revises: e1a2b3c4d5f6
Create Date: 2026-09-05
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "c7d8e9f0a1b2"
down_revision = "e1a2b3c4d5f6"
branch_labels = None
depends_on = None


def _catalog_columns() -> list[sa.Column]:
    """Columns every catalog table shares."""
    return [
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "category",
            sa.String(length=32),
            nullable=False,
            server_default="GENERAL",
        ),
        sa.Column(
            "tags",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column(
            "publish_status",
            sa.String(length=32),
            nullable=False,
            server_default="DRAFT",
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("changelog", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "origin", sa.String(length=32), nullable=False, server_default="ADMIN"
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "published_by_user_id", postgresql.UUID(as_uuid=True), nullable=True
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
    ]


def upgrade() -> None:
    op.create_table(
        "system_skill",
        *_catalog_columns(),
        sa.Column("built_in_skill_id", sa.String(), nullable=True),
        sa.Column("bundle_file_id", sa.String(), nullable=True),
        sa.Column("bundle_sha256", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(
            ["published_by_user_id"], ["user.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_system_skill_slug"),
        sa.CheckConstraint(
            "(built_in_skill_id IS NULL) <> (bundle_file_id IS NULL)",
            name="ck_system_skill_definition_source",
        ),
    )
    op.create_index(
        "ix_system_skill_publish_status", "system_skill", ["publish_status"]
    )

    op.create_table(
        "system_report_template",
        *_catalog_columns(),
        sa.Column("body", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["published_by_user_id"], ["user.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_system_report_template_slug"),
    )
    op.create_index(
        "ix_system_report_template_publish_status",
        "system_report_template",
        ["publish_status"],
    )

    op.create_table(
        "system_scenario",
        *_catalog_columns(),
        sa.Column(
            "rules", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'")
        ),
        sa.Column(
            "skill_slugs",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column("report_template_slug", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(
            ["published_by_user_id"], ["user.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_system_scenario_slug"),
    )
    op.create_index(
        "ix_system_scenario_publish_status", "system_scenario", ["publish_status"]
    )

    # Runtime-side pointers. A projection is the row with a catalog id and no
    # author; a fork carries both a catalog id and an author.
    op.add_column(
        "skill",
        sa.Column("system_skill_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column("skill", sa.Column("system_skill_version", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_skill_system_skill_id",
        "skill",
        "system_skill",
        ["system_skill_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_skill_system_skill_id", "skill", ["system_skill_id"])

    op.add_column(
        "scenario",
        sa.Column("system_scenario_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "scenario", sa.Column("system_scenario_version", sa.Integer(), nullable=True)
    )
    op.create_foreign_key(
        "fk_scenario_system_scenario_id",
        "scenario",
        "system_scenario",
        ["system_scenario_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_scenario_system_scenario_id", "scenario", ["system_scenario_id"])

    op.add_column(
        "report_template",
        sa.Column(
            "system_report_template_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
    )
    op.add_column(
        "report_template",
        sa.Column("system_report_template_version", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_report_template_system_report_template_id",
        "report_template",
        "system_report_template",
        ["system_report_template_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_report_template_system_report_template_id",
        "report_template",
        ["system_report_template_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_report_template_system_report_template_id", table_name="report_template"
    )
    op.drop_constraint(
        "fk_report_template_system_report_template_id",
        "report_template",
        type_="foreignkey",
    )
    op.drop_column("report_template", "system_report_template_version")
    op.drop_column("report_template", "system_report_template_id")

    op.drop_index("ix_scenario_system_scenario_id", table_name="scenario")
    op.drop_constraint(
        "fk_scenario_system_scenario_id", "scenario", type_="foreignkey"
    )
    op.drop_column("scenario", "system_scenario_version")
    op.drop_column("scenario", "system_scenario_id")

    op.drop_index("ix_skill_system_skill_id", table_name="skill")
    op.drop_constraint("fk_skill_system_skill_id", "skill", type_="foreignkey")
    op.drop_column("skill", "system_skill_version")
    op.drop_column("skill", "system_skill_id")

    op.drop_index("ix_system_scenario_publish_status", table_name="system_scenario")
    op.drop_table("system_scenario")
    op.drop_index(
        "ix_system_report_template_publish_status", table_name="system_report_template"
    )
    op.drop_table("system_report_template")
    op.drop_index("ix_system_skill_publish_status", table_name="system_skill")
    op.drop_table("system_skill")
