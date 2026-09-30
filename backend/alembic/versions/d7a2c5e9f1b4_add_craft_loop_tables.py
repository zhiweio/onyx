"""add craft_loop tables

Revision ID: d7a2c5e9f1b4
Revises: c8f1b4d7e9a3
Create Date: 2026-09-30

Supervised recurring task loops (QM loop port): the loop definition with
its ship-action policy (policy_version invalidates grants on edit), the
item ledger (claim/decision leases, attempts, reviewer guidance), held
outputs awaiting the ship decision, and standing human grants per ship
action at one policy version.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "d7a2c5e9f1b4"
down_revision = "c8f1b4d7e9a3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "craft_loop",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "playbook", postgresql.JSONB(), nullable=False, server_default="{}"
        ),
        sa.Column(
            "policy_version", sa.Integer(), nullable=False, server_default="1"
        ),
        sa.Column(
            "ship_actions", postgresql.JSONB(), nullable=False, server_default="[]"
        ),
        sa.Column(
            "success_condition", sa.Text(), nullable=False, server_default=""
        ),
        sa.Column("caps", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "state",
            sa.Enum(
                "enabled",
                "paused",
                "quarantined",
                "archived",
                native_enum=False,
                name="craftloopstate",
            ),
            nullable=False,
            server_default="enabled",
        ),
        sa.Column(
            "health",
            sa.Enum(
                "healthy",
                "degraded",
                "failing",
                "quarantined",
                native_enum=False,
                name="craftloophealth",
            ),
            nullable=False,
            server_default="healthy",
        ),
        sa.Column(
            "consecutive_failed_fires",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("trigger_cron", sa.String(length=128), nullable=True),
        sa.Column(
            "scenario_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("scenario.id", ondelete="SET NULL"),
            nullable=True,
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
    )
    op.create_index("ix_craft_loop_user", "craft_loop", ["user_id"])
    op.create_index("ix_craft_loop_state", "craft_loop", ["state"])

    op.create_table(
        "craft_loop_item",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "loop_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("craft_loop.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_key", sa.String(length=512), nullable=False),
        sa.Column("source_summary", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "status",
            sa.Enum(
                "queued",
                "in_progress",
                "ready",
                "shipped",
                "failed",
                "skipped",
                native_enum=False,
                name="craftloopitemstatus",
            ),
            nullable=False,
            server_default="queued",
        ),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("guidance", sa.Text(), nullable=True),
        sa.Column(
            "proposal", postgresql.JSONB(), nullable=False, server_default="{}"
        ),
        sa.Column("claim_token", sa.String(length=64), nullable=True),
        sa.Column("claim_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_token", sa.String(length=64), nullable=True),
        sa.Column("decision_expires_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.UniqueConstraint("loop_id", "source_key", name="uq_craft_loop_item_source"),
    )
    op.create_index(
        "ix_craft_loop_item_status", "craft_loop_item", ["loop_id", "status"]
    )

    op.create_table(
        "craft_loop_output",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "loop_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("craft_loop.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("craft_loop_item.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ship_action", sa.String(length=128), nullable=False),
        sa.Column("label", sa.String(length=256), nullable=True),
        sa.Column("title", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "state",
            sa.Enum(
                "staged",
                "ready",
                "shipping",
                "shipped",
                "returned",
                native_enum=False,
                name="craftloopoutputstate",
            ),
            nullable=False,
            server_default="staged",
        ),
        sa.Column(
            "decided_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("external_ref", sa.Text(), nullable=True),
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
    )
    op.create_index(
        "ix_craft_loop_output_state", "craft_loop_output", ["loop_id", "state"]
    )

    op.create_table(
        "craft_loop_grant",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "loop_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("craft_loop.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ship_action", sa.String(length=128), nullable=False),
        sa.Column("label", sa.String(length=256), nullable=True),
        sa.Column(
            "actor_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("policy_version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_craft_loop_grant_loop", "craft_loop_grant", ["loop_id", "ship_action"]
    )


def downgrade() -> None:
    op.drop_table("craft_loop_grant")
    op.drop_table("craft_loop_output")
    op.drop_table("craft_loop_item")
    op.drop_table("craft_loop")
    for enum_name in (
        "craftloopstate",
        "craftloophealth",
        "craftloopitemstatus",
        "craftloopoutputstate",
    ):
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
