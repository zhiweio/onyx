"""report template catalog

Revision ID: d5e6f7a8b9c0
Revises: c3d4e5f6a7b8
Create Date: 2026-08-30
"""

import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "d5e6f7a8b9c0"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None

SEED_TEMPLATES = (
    (
        "compliance_risk",
        "合规风险预警",
        "Tax compliance risk brief for an entity.",
        """# 合规风险预警报告

Use this structure for chat Tax Personas and Deep Research.

1. **对象** — 企业名称、统一社会信用代码、行业、地区
2. **结论** — 风险等级与一句话原因
3. **发现** — 每条含来源 URL、source_id、trust_tier、日期
4. **政策依据** — 文号、发文机关、生效日期
5. **未覆盖来源** — 插件未配置或查询失败
6. **建议动作** — 可执行的下一步
""",
    ),
    (
        "policy_trend",
        "政策趋势研判",
        "Tax policy trend brief for a tax type, industry, or region.",
        """# 政策趋势研判报告

Use this structure for chat Tax Personas and Deep Research.

1. **范围** — 税种、行业、地区、时间窗
2. **变化摘要** — 官方政策与新闻分列
3. **影响对象** — 谁受影响、如何受影响
4. **时间线** — 发布、生效、过渡
5. **来源** — URL、source_id、trust_tier
6. **待核实** — 缺文号或仅有新闻转述的条目
""",
    ),
    (
        "target_landscape",
        "靶点文献与竞争格局",
        "Map a target, mechanism, and competing programs.",
        """# 靶点文献与竞争格局报告

1. **靶点与机制** — 靶点、通路、适应症
2. **关键证据** — 文献与注册披露，含引用
3. **竞争格局** — 在研资产、阶段、东家
4. **差异化** — 机制、给药、安全窗口
5. **空白与风险** — 证据缺口与已知失败
6. **建议下一步** — 可执行的检索或验证
""",
    ),
    (
        "patent_fto",
        "专利自由实施评估",
        "Freedom-to-operate and patent landscape brief.",
        """# 专利自由实施评估

1. **范围** — 化合物/制剂/用途、地区、时间
2. **核心专利族** — 权利人、状态、到期
3. **权利要求对照** — 与拟实施方案的重叠
4. **规避空间** — 可调整的结构或用途
5. **文献与公开** — 可能影响新颖性的披露
6. **结论** — FTO 风险等级与建议动作
""",
    ),
    (
        "clinical_pipeline",
        "临床管线扫描",
        "Competing trials and pipeline design for an indication.",
        """# 临床管线扫描

1. **适应症与人群** — 分期、生物标志物
2. **在研管线** — 资产、东家、阶段
3. **试验设计** — 终点、对照、入排
4. **读出时间** — 已披露与预计节点
5. **竞争位置** — 相对进度与差异
6. **建议关注** — 需跟踪的试验或披露
""",
    ),
    (
        "cmc_quality",
        "CMC 与质量风险",
        "CMC and quality risk from labels, guidance, and recalls.",
        """# CMC 与质量风险简报

1. **产品与剂型** — 成分、规格、工艺要点
2. **药学风险** — 稳定性、杂质、包材
3. **指导原则** — 适用 CMC / 质量指南
4. **召回与缺陷** — 公开质量事件
5. **标签与规格** — 与拟开发方案的差距
6. **建议动作** — 需补的研究或对照
""",
    ),
)


def upgrade() -> None:
    op.create_table(
        "report_template",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("author_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "is_builtin",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
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
        sa.ForeignKeyConstraint(["author_user_id"], ["user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_report_template_slug"),
    )

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
    op.bulk_insert(
        template_table,
        [
            {
                "id": uuid.uuid4(),
                "slug": slug,
                "name": name,
                "description": description,
                "body": body,
                "author_user_id": None,
                "is_builtin": True,
            }
            for slug, name, description, body in SEED_TEMPLATES
        ],
    )

    op.execute(
        sa.text(
            """
            INSERT INTO report_template (id, slug, name, description, body, author_user_id, is_builtin)
            SELECT gen_random_uuid(), s.report_template, s.report_template, '',
                   '# ' || s.report_template, NULL, false
            FROM (
                SELECT DISTINCT report_template
                FROM scenario
                WHERE report_template IS NOT NULL AND btrim(report_template) <> ''
            ) s
            WHERE NOT EXISTS (
                SELECT 1 FROM report_template t WHERE t.slug = s.report_template
            )
            """
        )
    )


def downgrade() -> None:
    op.drop_table("report_template")
