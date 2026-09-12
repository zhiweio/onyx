"""detach implicit Untitled Craft projects

Revision ID: d6e7f8a9b0c1
Revises: f8c9d0e1f2a3
Create Date: 2026-09-12
"""

from alembic import op

revision = "d6e7f8a9b0c1"
down_revision = "f8c9d0e1f2a3"
branch_labels = None
depends_on = None

_IMPLICIT = """
    name = 'Untitled project'
    AND description = ''
    AND (instructions IS NULL OR btrim(instructions) = '')
"""


def upgrade() -> None:
    op.execute(
        f"""
        UPDATE build_session
        SET project_id = NULL
        WHERE project_id IN (
            SELECT id FROM craft_project WHERE {_IMPLICIT}
        )
        """
    )
    op.execute(
        f"""
        UPDATE craft_job
        SET project_id = NULL
        WHERE project_id IN (
            SELECT id FROM craft_project WHERE {_IMPLICIT}
        )
        """
    )
    op.execute(
        f"""
        UPDATE long_term_memory
        SET project_id = NULL
        WHERE project_id IN (
            SELECT id FROM craft_project WHERE {_IMPLICIT}
        )
        """
    )
    op.execute(
        f"""
        DELETE FROM craft_project_file
        WHERE project_id IN (
            SELECT id FROM craft_project WHERE {_IMPLICIT}
        )
        """
    )
    op.execute(f"DELETE FROM craft_project WHERE {_IMPLICIT}")


def downgrade() -> None:
    pass
