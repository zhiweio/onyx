"""add persona.agent_budget

Revision ID: f4a9c2e6b8d1
Revises: d1f6a8b2c4e7
Create Date: 2026-09-26

Per-assistant agent loop budget overrides (chat tool-loop cycles, extension
cycles, token ceiling). None or missing fields inherit the deployment-wide
env defaults; the payload is validated by onyx.chat.agent_budget.AgentBudget
before anything reads it, so malformed rows degrade to the global budget.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "f4a9c2e6b8d1"
down_revision = "d1f6a8b2c4e7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "persona",
        sa.Column("agent_budget", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("persona", "agent_budget")
