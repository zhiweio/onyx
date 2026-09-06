"""seed biomed skills and scenario packs

Revision ID: b2c3d4e5f6a7
Revises: a9c8d7e6f5b4
Create Date: 2026-08-30
"""

import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "b2c3d4e5f6a7"
down_revision = "a9c8d7e6f5b4"
branch_labels = None
depends_on = None


BIOMED_SKILLS = (
    (
        "biomed-literature",
        "Research a drug target, mechanism, or competitive landscape from cited literature.",
    ),
    (
        "biomed-patent-fto",
        "Draft a freedom-to-operate and patent landscape brief.",
    ),
    (
        "biomed-clinical-intel",
        "Map clinical pipelines and competing trials for an indication or asset.",
    ),
    (
        "biomed-cmc-quality",
        "Assess CMC and quality risk from public labels, guidances, and recall notices.",
    ),
)

BIOMED_PACKS = (
    (
        "靶点文献与竞争格局",
        "从文献和注册披露整理靶点机制与竞争格局。",
        ("biomed-literature", "biomed-clinical-intel"),
        "target_landscape",
    ),
    (
        "专利自由实施评估",
        "组合专利检索与文献，评估自由实施风险。",
        ("biomed-patent-fto", "biomed-literature"),
        "patent_fto",
    ),
    (
        "临床管线扫描",
        "扫描适应症竞品试验与管线设计。",
        ("biomed-clinical-intel", "biomed-literature"),
        "clinical_pipeline",
    ),
    (
        "CMC 与质量风险简报",
        "从公开标签、指导原则和召回信息评估药学与质量风险。",
        ("biomed-cmc-quality", "biomed-literature"),
        "cmc_quality",
    ),
)


def upgrade() -> None:
    conn = op.get_bind()
    skill_table = sa.table(
        "skill",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("name", sa.String),
        sa.column("description", sa.Text),
        sa.column("built_in_skill_id", sa.String),
        sa.column("bundle_file_id", sa.String),
        sa.column("bundle_sha256", sa.String),
        sa.column("is_valid", sa.Boolean),
        sa.column("author_user_id", postgresql.UUID(as_uuid=True)),
        sa.column("public_permission", sa.String),
    )
    skill_ids: dict[str, uuid.UUID] = {}
    for skill_key, description in BIOMED_SKILLS:
        existing = conn.execute(
            sa.select(skill_table.c.id).where(
                skill_table.c.built_in_skill_id == skill_key
            )
        ).first()
        if existing is not None:
            skill_ids[skill_key] = existing[0]
            continue
        new_id = uuid.uuid4()
        conn.execute(
            sa.insert(skill_table).values(
                id=new_id,
                name=skill_key,
                description=description,
                built_in_skill_id=skill_key,
                bundle_file_id=None,
                bundle_sha256=None,
                is_valid=True,
                author_user_id=None,
                public_permission="VIEWER",
            )
        )
        skill_ids[skill_key] = new_id

    scenario_table = sa.table(
        "scenario",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("name", sa.String),
        sa.column("description", sa.Text),
        sa.column("author_user_id", postgresql.UUID(as_uuid=True)),
        sa.column("public_permission", sa.String),
        sa.column("rules", postgresql.JSONB()),
        sa.column("report_template", sa.String),
    )
    scenario_skill = sa.table(
        "scenario__skill",
        sa.column("scenario_id", postgresql.UUID(as_uuid=True)),
        sa.column("skill_id", postgresql.UUID(as_uuid=True)),
        sa.column("sort_order", sa.Integer),
    )

    tax_rows = conn.execute(
        sa.select(scenario_table.c.id, scenario_table.c.rules).where(
            scenario_table.c.name.in_(("合规风险预警", "政策趋势研判"))
        )
    ).fetchall()
    for scenario_id, rules in tax_rows:
        merged = dict(rules or {})
        if merged.get("domain") == "tax":
            continue
        merged["domain"] = "tax"
        conn.execute(
            sa.update(scenario_table)
            .where(scenario_table.c.id == scenario_id)
            .values(rules=merged)
        )

    for name, description, skill_keys, template in BIOMED_PACKS:
        existing = conn.execute(
            sa.select(scenario_table.c.id).where(scenario_table.c.name == name)
        ).first()
        if existing is not None:
            continue
        scenario_id = uuid.uuid4()
        bound = [skill_ids[key] for key in skill_keys]
        conn.execute(
            sa.insert(scenario_table).values(
                id=scenario_id,
                name=name,
                description=description,
                author_user_id=None,
                public_permission="VIEWER",
                rules={
                    "domain": "biomed",
                    "always_skill_ids": [str(skill_id) for skill_id in bound],
                },
                report_template=template,
            )
        )
        for sort_order, skill_id in enumerate(bound):
            conn.execute(
                sa.insert(scenario_skill).values(
                    scenario_id=scenario_id,
                    skill_id=skill_id,
                    sort_order=sort_order,
                )
            )


def downgrade() -> None:
    conn = op.get_bind()
    for name, _description, _skill_keys, _template in BIOMED_PACKS:
        conn.execute(sa.text("DELETE FROM scenario WHERE name = :name"), {"name": name})
    for skill_key, _description in BIOMED_SKILLS:
        conn.execute(
            sa.text("DELETE FROM skill WHERE built_in_skill_id = :skill_id"),
            {"skill_id": skill_key},
        )
