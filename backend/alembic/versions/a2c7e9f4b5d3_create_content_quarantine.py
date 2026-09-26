"""create content_quarantine table

Revision ID: a2c7e9f4b5d3
Revises: f4a9c2e6b8d1
Create Date: 2026-09-27

Inbound-content quarantine + human release decision (the WS6 enforce-mode
closure). One row per quarantined URL per session, deduped by the writer;
the stashed original body lives in Redis and an approved release serves it
without re-fetching.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "a2c7e9f4b5d3"
down_revision = "f4a9c2e6b8d1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "content_quarantine",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "session_id",
            sa.UUID(),
            sa.ForeignKey("build_session.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("url_host", sa.String(), nullable=False),
        sa.Column("url_path", sa.String(), nullable=False, server_default=""),
        sa.Column("url_hash", sa.String(64), nullable=False),
        sa.Column("verdict", sa.String(32), nullable=False),
        sa.Column("patterns_matched", postgresql.JSONB(), nullable=False),
        sa.Column("evidence_excerpt", sa.Text(), nullable=False),
        sa.Column(
            "decision",
            sa.Enum(
                "PENDING",
                "APPROVED",
                "DENIED",
                name="contentquarantinedecision",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "scope",
            sa.Enum(
                "ONCE", "SESSION", "HOST", name="contentreleasescope", native_enum=False
            ),
            nullable=True,
        ),
        sa.Column(
            "decided_by",
            sa.UUID(),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_content_quarantine_session",
        "content_quarantine",
        ["session_id"],
    )
    op.create_index(
        "ix_content_quarantine_session_hash",
        "content_quarantine",
        ["session_id", "url_hash"],
    )


def downgrade() -> None:
    op.drop_index("ix_content_quarantine_session_hash", table_name="content_quarantine")
    op.drop_index("ix_content_quarantine_session", table_name="content_quarantine")
    op.drop_table("content_quarantine")
