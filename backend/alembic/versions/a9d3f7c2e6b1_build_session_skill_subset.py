"""Build-session skill subset column.

The per-session catalog: ``.opencode/skills`` links only this subset, so
opencode's skill-tool description (name+description of every linked skill,
sent on each LLM call) stays small. NULL keeps the legacy behavior — the
full managed catalog.

Revision ID: a9d3f7c2e6b1
Revises: b4d2e8f6a9c1
Create Date: 2026-10-05
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "a9d3f7c2e6b1"
down_revision = "b4d2e8f6a9c1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "build_session",
        sa.Column("skill_slugs", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("build_session", "skill_slugs")
