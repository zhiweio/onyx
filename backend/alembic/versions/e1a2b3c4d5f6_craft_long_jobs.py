"""craft long jobs, ingest skills, and scenario packs

Revision ID: e1a2b3c4d5f6
Revises: d8c2f1a90b47
Create Date: 2026-09-05
"""

import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "e1a2b3c4d5f6"
down_revision = "d8c2f1a90b47"
branch_labels = None
depends_on = None


LONG_JOB_SKILLS = (
    (
        "long-job-protocol",
        "Shared file layout and phase rules for Craft long jobs.",
    ),
    (
        "document-ingest",
        "Parse project and library files into MANIFEST plus extracted JSON and CSV.",
    ),
    (
        "biomed-initiation",
        "Plan and write a cited drug-program initiation report.",
    ),
    (
        "tax-recon-supplier",
        "Reconcile supplier payables against invoices or statements.",
    ),
    (
        "tax-bank-ledger",
        "Merge multi-bank statements into one ledger.",
    ),
    (
        "tax-expense-rollup",
        "Roll subsidiary expense claims into one template.",
    ),
    (
        "tax-invoice-compliance",
        "Scan invoices for required fields, tax IDs, rates, and header mismatches.",
    ),
    (
        "tax-opex-variance",
        "Compare department opex across periods.",
    ),
    (
        "tax-ar-risk",
        "Rank high-risk AR customers from aging, collections, and optional credit MCP.",
    ),
)

REPORT_TEMPLATES = (
    (
        "initiation_report",
        "Drug program initiation",
        "Cited initiation report outline.",
        "# Initiation report\n\n## Asset and indication\n\n## Evidence\n\n## Risks\n\n## Open questions\n",
    ),
    (
        "supplier_recon",
        "Supplier reconciliation",
        "Payables vs invoices.",
        "# Supplier reconciliation\n\n## Scope\n\n## Match summary\n\n## Exceptions\n",
    ),
    (
        "bank_ledger",
        "Bank ledger rollup",
        "Multi-bank statement merge.",
        "# Bank ledger\n\n## Banks and period\n\n## Combined ledger\n\n## Balance check\n",
    ),
    (
        "expense_rollup",
        "Expense rollup",
        "Subsidiary claims by template.",
        "# Expense rollup\n\n## Template fields\n\n## Company x department\n\n## Outliers\n",
    ),
    (
        "invoice_compliance",
        "Invoice compliance",
        "Invoice exception list.",
        "# Invoice compliance\n\n## Files scanned\n\n## Exceptions\n",
    ),
    (
        "opex_variance",
        "Opex variance",
        "Period expense comparison.",
        "# Opex variance\n\n## Periods\n\n## Large moves\n\n## Unexplained\n",
    ),
    (
        "ar_risk",
        "AR risk list",
        "High-risk customers.",
        "# AR risk\n\n## Aging\n\n## External flags\n\n## Priority list\n",
    ),
)

LONG_JOB_PACKS = (
    (
        "医药立项报告",
        "跨文献、临床、专利与 CMC 的立项作业。",
        (
            "long-job-protocol",
            "biomed-initiation",
            "biomed-literature",
            "biomed-clinical-intel",
            "biomed-patent-fto",
            "biomed-cmc-quality",
        ),
        "initiation_report",
        "biomed",
    ),
    (
        "供应商对账",
        "应付与发票或对账单对齐，输出差异表。",
        ("long-job-protocol", "document-ingest", "tax-recon-supplier"),
        "supplier_recon",
        "tax",
    ),
    (
        "多银行流水汇总",
        "多银行流水归一并做余额调节。",
        ("long-job-protocol", "document-ingest", "tax-bank-ledger"),
        "bank_ledger",
        "tax",
    ),
    (
        "子公司报销汇总",
        "按模板抽取报销单并按公司部门透视。",
        ("long-job-protocol", "document-ingest", "tax-expense-rollup"),
        "expense_rollup",
        "tax",
    ),
    (
        "发票合规扫描",
        "批量发票必填项与税号税率检查。",
        ("long-job-protocol", "document-ingest", "tax-invoice-compliance"),
        "invoice_compliance",
        "tax",
    ),
    (
        "部门费用波动",
        "多期费用同比环比与异常科目。",
        ("long-job-protocol", "document-ingest", "tax-opex-variance"),
        "opex_variance",
        "tax",
    ),
    (
        "应收高风险客户",
        "账龄、回款与外部征信汇总。",
        ("long-job-protocol", "document-ingest", "tax-ar-risk"),
        "ar_risk",
        "tax",
    ),
)


def upgrade() -> None:
    op.create_table(
        "craft_job",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("scenario_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("domain", sa.String(length=32), nullable=False, server_default="general"),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("phases", postgresql.JSONB(), nullable=False),
        sa.Column("current_phase_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_budget_seconds", sa.Integer(), nullable=False),
        sa.Column("phase_budget_seconds", sa.Integer(), nullable=False),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["build_session.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["craft_project.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["scenario_id"], ["scenario.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_craft_job_user_created", "craft_job", ["user_id", "created_at"])
    op.create_index("ix_craft_job_session_id", "craft_job", ["session_id"])
    op.create_index("ix_craft_job_status", "craft_job", ["status"])

    op.create_table(
        "craft_job_specialist",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=64), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["job_id"], ["craft_job.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["session_id"], ["build_session.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint("session_id", name="uq_craft_job_specialist_session_id"),
    )
    op.create_index(
        "ix_craft_job_specialist_job_id", "craft_job_specialist", ["job_id"]
    )

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
    for skill_key, description in LONG_JOB_SKILLS:
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

    for extra in (
        "biomed-literature",
        "biomed-clinical-intel",
        "biomed-patent-fto",
        "biomed-cmc-quality",
    ):
        row = conn.execute(
            sa.select(skill_table.c.id).where(skill_table.c.built_in_skill_id == extra)
        ).first()
        if row is not None:
            skill_ids[extra] = row[0]

    template_table = sa.table(
        "report_template",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("slug", sa.String),
        sa.column("name", sa.String),
        sa.column("description", sa.Text),
        sa.column("body", sa.Text),
        sa.column("author_user_id", postgresql.UUID(as_uuid=True)),
        sa.column("is_builtin", sa.Boolean),
    )
    for slug, name, description, body in REPORT_TEMPLATES:
        existing = conn.execute(
            sa.select(template_table.c.id).where(template_table.c.slug == slug)
        ).first()
        if existing is not None:
            continue
        conn.execute(
            sa.insert(template_table).values(
                id=uuid.uuid4(),
                slug=slug,
                name=name,
                description=description,
                body=body,
                author_user_id=None,
                is_builtin=True,
            )
        )

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
    for name, description, skill_keys, template, domain in LONG_JOB_PACKS:
        existing = conn.execute(
            sa.select(scenario_table.c.id).where(scenario_table.c.name == name)
        ).first()
        if existing is not None:
            continue
        bound = [skill_ids[key] for key in skill_keys if key in skill_ids]
        if not bound:
            continue
        scenario_id = uuid.uuid4()
        conn.execute(
            sa.insert(scenario_table).values(
                id=scenario_id,
                name=name,
                description=description,
                author_user_id=None,
                public_permission="VIEWER",
                rules={
                    "domain": domain,
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
    for name, _description, _skill_keys, _template, _domain in LONG_JOB_PACKS:
        conn.execute(sa.text("DELETE FROM scenario WHERE name = :name"), {"name": name})
    for slug, _name, _description, _body in REPORT_TEMPLATES:
        conn.execute(
            sa.text("DELETE FROM report_template WHERE slug = :slug"),
            {"slug": slug},
        )
    for skill_key, _description in LONG_JOB_SKILLS:
        conn.execute(
            sa.text("DELETE FROM skill WHERE built_in_skill_id = :skill_id"),
            {"skill_id": skill_key},
        )
    op.drop_index("ix_craft_job_specialist_job_id", table_name="craft_job_specialist")
    op.drop_table("craft_job_specialist")
    op.drop_index("ix_craft_job_status", table_name="craft_job")
    op.drop_index("ix_craft_job_session_id", table_name="craft_job")
    op.drop_index("ix_craft_job_user_created", table_name="craft_job")
    op.drop_table("craft_job")
