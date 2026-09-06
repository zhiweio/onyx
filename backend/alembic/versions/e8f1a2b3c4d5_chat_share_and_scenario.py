"""chat session member shares, scenarios, tax live query tool

Revision ID: e8f1a2b3c4d5
Revises: 34fe28843029
Create Date: 2026-08-29
"""

import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "e8f1a2b3c4d5"
down_revision = "34fe28843029"
branch_labels = None
depends_on = None


TAX_LIVE_QUERY_TOOL = {
    "name": "TaxLiveQueryTool",
    "display_name": "Tax live query",
    "description": (
        "Query China tax/official/news sources and commercial MCP plugins "
        "(Qixinbao, PatSnap) at analysis time. Returns cited NormalizedRecords."
    ),
    "in_code_tool_id": "TaxLiveQueryTool",
    "enabled": True,
}


def upgrade() -> None:
    op.create_table(
        "chat_session__user",
        sa.Column("chat_session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "permission",
            sa.String(),
            nullable=False,
            server_default="VIEWER",
        ),
        sa.ForeignKeyConstraint(
            ["chat_session_id"], ["chat_session.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("chat_session_id", "user_id"),
    )
    op.create_index(
        "ix_chat_session__user_user_id", "chat_session__user", ["user_id"]
    )

    op.create_table(
        "chat_session__user_group",
        sa.Column("chat_session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_group_id", sa.Integer(), nullable=False),
        sa.Column(
            "permission",
            sa.String(),
            nullable=False,
            server_default="VIEWER",
        ),
        sa.ForeignKeyConstraint(
            ["chat_session_id"], ["chat_session.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_group_id"], ["user_group.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("chat_session_id", "user_group_id"),
    )
    op.create_index(
        "ix_chat_session__user_group_user_group_id",
        "chat_session__user_group",
        ["user_group_id"],
    )

    op.create_table(
        "scenario",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("author_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("public_permission", sa.String(), nullable=True),
        sa.Column(
            "rules",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("report_template", sa.String(length=64), nullable=True),
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
        sa.ForeignKeyConstraint(["author_user_id"], ["user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "scenario__skill",
        sa.Column("scenario_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("skill_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["scenario_id"], ["scenario.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["skill_id"], ["skill.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("scenario_id", "skill_id"),
    )

    op.create_table(
        "scenario__user",
        sa.Column("scenario_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "permission",
            sa.String(),
            nullable=False,
            server_default="VIEWER",
        ),
        sa.ForeignKeyConstraint(["scenario_id"], ["scenario.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("scenario_id", "user_id"),
    )
    op.create_index("ix_scenario__user_user_id", "scenario__user", ["user_id"])

    op.create_table(
        "scenario__user_group",
        sa.Column("scenario_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_group_id", sa.Integer(), nullable=False),
        sa.Column(
            "permission",
            sa.String(),
            nullable=False,
            server_default="VIEWER",
        ),
        sa.ForeignKeyConstraint(["scenario_id"], ["scenario.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["user_group_id"], ["user_group.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("scenario_id", "user_group_id"),
    )
    op.create_index(
        "ix_scenario__user_group_user_group_id",
        "scenario__user_group",
        ["user_group_id"],
    )

    op.add_column(
        "build_session",
        sa.Column("scenario_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_build_session_scenario_id",
        "build_session",
        "scenario",
        ["scenario_id"],
        ["id"],
        ondelete="SET NULL",
    )

    conn = op.get_bind()
    existing = conn.execute(
        sa.text("SELECT id FROM tool WHERE in_code_tool_id = :in_code_tool_id"),
        {"in_code_tool_id": TAX_LIVE_QUERY_TOOL["in_code_tool_id"]},
    ).fetchone()
    if existing:
        conn.execute(
            sa.text(
                """
                UPDATE tool
                SET name = :name,
                    display_name = :display_name,
                    description = :description
                WHERE in_code_tool_id = :in_code_tool_id
                """
            ),
            TAX_LIVE_QUERY_TOOL,
        )
        tool_id = existing[0]
    else:
        conn.execute(
            sa.text(
                """
                INSERT INTO tool (name, display_name, description, in_code_tool_id, enabled)
                VALUES (:name, :display_name, :description, :in_code_tool_id, :enabled)
                """
            ),
            TAX_LIVE_QUERY_TOOL,
        )
        result = conn.execute(
            sa.text("SELECT id FROM tool WHERE in_code_tool_id = :in_code_tool_id"),
            {"in_code_tool_id": TAX_LIVE_QUERY_TOOL["in_code_tool_id"]},
        ).fetchone()
        tool_id = result[0] if result else None

    if tool_id is not None:
        persona_ids = conn.execute(sa.text("SELECT id FROM persona")).fetchall()
        for (persona_id,) in persona_ids:
            exists = conn.execute(
                sa.text(
                    """
                    SELECT 1 FROM persona__tool
                    WHERE persona_id = :persona_id AND tool_id = :tool_id
                    """
                ),
                {"persona_id": persona_id, "tool_id": tool_id},
            ).fetchone()
            if not exists:
                conn.execute(
                    sa.text(
                        """
                        INSERT INTO persona__tool (persona_id, tool_id)
                        VALUES (:persona_id, :tool_id)
                        """
                    ),
                    {"persona_id": persona_id, "tool_id": tool_id},
                )

    _skill_table = sa.table(
        "skill",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("name", sa.String),
        sa.column("description", sa.Text),
        sa.column("built_in_skill_id", sa.String),
        sa.column("bundle_file_id", sa.String),
        sa.column("bundle_sha256", sa.String),
        sa.column("author_user_id", postgresql.UUID(as_uuid=True)),
        sa.column("public_permission", sa.String),
    )
    tax_skills = (
        (
            "tax-compliance",
            "Assess China tax compliance risk using live policy, enforcement, and MCP sources.",
        ),
        (
            "tax-policy-trend",
            "Research China tax policy trends and write a cited outlook.",
        ),
    )
    skill_ids: dict[str, uuid.UUID] = {}
    for skill_id, description in tax_skills:
        existing_skill = conn.execute(
            sa.select(_skill_table.c.id).where(
                _skill_table.c.built_in_skill_id == skill_id
            )
        ).first()
        if existing_skill is not None:
            skill_ids[skill_id] = existing_skill[0]
            continue
        new_id = uuid.uuid4()
        conn.execute(
            sa.insert(_skill_table).values(
                id=new_id,
                name=skill_id,
                description=description,
                built_in_skill_id=skill_id,
                bundle_file_id=None,
                bundle_sha256=None,
                author_user_id=None,
                public_permission="VIEWER",
            )
        )
        skill_ids[skill_id] = new_id

    _scenario_table = sa.table(
        "scenario",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("name", sa.String),
        sa.column("description", sa.Text),
        sa.column("author_user_id", postgresql.UUID(as_uuid=True)),
        sa.column("public_permission", sa.String),
        sa.column("rules", postgresql.JSONB()),
        sa.column("report_template", sa.String),
    )
    _scenario_skill = sa.table(
        "scenario__skill",
        sa.column("scenario_id", postgresql.UUID(as_uuid=True)),
        sa.column("skill_id", postgresql.UUID(as_uuid=True)),
        sa.column("sort_order", sa.Integer),
    )
    for name, description, skill_key, template in (
        (
            "合规风险预警",
            "企业税务合规与违法案件风险预警。",
            "tax-compliance",
            "compliance_risk",
        ),
        (
            "政策趋势研判",
            "税种政策变化与趋势研判。",
            "tax-policy-trend",
            "policy_trend",
        ),
    ):
        existing_scenario = conn.execute(
            sa.select(_scenario_table.c.id).where(_scenario_table.c.name == name)
        ).first()
        if existing_scenario is not None:
            continue
        scenario_id = uuid.uuid4()
        bound_skill = skill_ids[skill_key]
        conn.execute(
            sa.insert(_scenario_table).values(
                id=scenario_id,
                name=name,
                description=description,
                author_user_id=None,
                public_permission="VIEWER",
                rules={"always_skill_ids": [str(bound_skill)]},
                report_template=template,
            )
        )
        conn.execute(
            sa.insert(_scenario_skill).values(
                scenario_id=scenario_id,
                skill_id=bound_skill,
                sort_order=0,
            )
        )


def downgrade() -> None:
    op.drop_constraint(
        "fk_build_session_scenario_id", "build_session", type_="foreignkey"
    )
    op.drop_column("build_session", "scenario_id")
    op.drop_table("scenario__user_group")
    op.drop_table("scenario__user")
    op.drop_table("scenario__skill")
    op.drop_table("scenario")
    op.drop_table("chat_session__user_group")
    op.drop_table("chat_session__user")
