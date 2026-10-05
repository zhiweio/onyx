"""Per-project long-term memory switch for Craft.

A project owner can enable long-term memory for their project's sessions
without the global per-user flag: ``craft_project.memory_enabled`` gates
recall/writes together with ``user.craft_use_long_term_memory`` (either
enables).

Revision ID: a7c9d2e5b8f4
Revises: f2b8e4a6c1d9
Create Date: 2026-10-05
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "a7c9d2e5b8f4"
down_revision = "f2b8e4a6c1d9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "craft_project",
        sa.Column(
            "memory_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("craft_project", "memory_enabled")
