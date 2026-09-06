"""Declarative inventory of the catalog content that ships with Onyx.

The manifest is the single source of truth for built-in gallery content. It is
deliberately data, not migrations: ``sync_builtin_system_catalog`` reconciles it
into the catalog at startup, so adding content is a manifest edit plus its
markdown body.

Skill bodies are not repeated here — a skill entry points at an on-disk built-in
under ``onyx/skills/builtin/<id>/``, which stays the one place skill content
lives.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Final

import yaml
from pydantic import BaseModel, ConfigDict, Field

from onyx.db.enums import ReportTemplateKind, SystemCatalogCategory
from onyx.skills.models import SKILL_NAME_PATTERN

_REPORT_TEMPLATE_DIR: Final[Path] = Path(__file__).parent / "report_templates"
_SCENARIO_DIR: Final[Path] = Path(__file__).parent / "scenarios"


class BuiltInSkillEntry(BaseModel):
    """A gallery entry backed by an on-disk built-in skill."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    # The slug doubles as the projected skill's name and sandbox directory, so
    # it follows the Agent Skills shape.
    slug: str = Field(pattern=SKILL_NAME_PATTERN.pattern, max_length=64)
    name: str
    description: str
    category: SystemCatalogCategory
    tags: tuple[str, ...] = ()
    built_in_skill_id: str


class BuiltInReportTemplateEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    slug: str
    name: str
    description: str
    category: SystemCatalogCategory
    tags: tuple[str, ...] = ()
    # File under ``report_templates/``. Bodies live on disk because they are
    # long prose that reads badly inside a Python literal.
    body_file: str
    kind: ReportTemplateKind = ReportTemplateKind.DOCX
    # Official Word builder slug. Defaults to ``slug``.
    builder: str | None = None

    def read_body(self) -> str:
        path = _REPORT_TEMPLATE_DIR / self.body_file
        if not path.is_file():
            raise ValueError(f"Missing report template body: {self.body_file}")
        return path.read_text(encoding="utf-8").strip()

    def builder_slug(self) -> str:
        return self.builder or self.slug


class BuiltInScenarioEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    slug: str
    name: str
    description: str
    category: SystemCatalogCategory
    tags: tuple[str, ...] = ()
    skill_slugs: tuple[str, ...] = ()
    report_template_slug: str | None = None
    # Playbook YAML under ``scenarios/``. Depth lives here, not in the tuple.
    playbook_file: str
    # Name of a pre-existing workspace scenario seeded by an older migration.
    # The sync adopts that row instead of creating a duplicate pack.
    adopt_runtime_name: str | None = None

    def read_rules(self) -> dict[str, Any]:
        path = _SCENARIO_DIR / self.playbook_file
        if not path.is_file():
            raise ValueError(f"Missing scenario playbook: {self.playbook_file}")
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError(f"Playbook must be a mapping: {self.playbook_file}")
        return loaded


BUILT_IN_SKILL_ENTRIES: Final[tuple[BuiltInSkillEntry, ...]] = (
    # ── documents ────────────────────────────────────────────────────────
    BuiltInSkillEntry(
        slug="pptx",
        name="PowerPoint 演示文稿",
        description="创建、编辑和读取 .pptx 演示文稿，支持模板、图表和缩略图预览。",
        category=SystemCatalogCategory.DOCUMENT,
        tags=("pptx", "slides", "演示文稿"),
        built_in_skill_id="pptx",
    ),
    BuiltInSkillEntry(
        slug="docx",
        name="Word 文档",
        description="创建和编辑 .docx 文档，支持模板占位符填充、批注与修订读取。",
        category=SystemCatalogCategory.DOCUMENT,
        tags=("docx", "word", "文档"),
        built_in_skill_id="docx",
    ),
    BuiltInSkillEntry(
        slug="xlsx",
        name="Excel 电子表格",
        description="读写 .xlsx 工作簿，支持公式重算、大表分块读取和格式化输出。",
        category=SystemCatalogCategory.DOCUMENT,
        tags=("xlsx", "excel", "表格"),
        built_in_skill_id="xlsx",
    ),
    BuiltInSkillEntry(
        slug="pdf",
        name="PDF 处理",
        description="提取 PDF 文本与表格，合并拆分页面，填写 AcroForm 表单字段。",
        category=SystemCatalogCategory.DOCUMENT,
        tags=("pdf", "表单", "提取"),
        built_in_skill_id="pdf",
    ),
    # ── general office ───────────────────────────────────────────────────
    BuiltInSkillEntry(
        slug="meeting-notes",
        name="会议纪要",
        description="把转写稿或零散记录整理成含决议与行动项的结构化会议纪要。",
        category=SystemCatalogCategory.OFFICE,
        tags=("会议纪要", "行动项", "minutes"),
        built_in_skill_id="meeting-notes",
    ),
    BuiltInSkillEntry(
        slug="data-analysis",
        name="数据分析",
        description="分析表格数据并给出结论与支撑数字，含数据质量检查。",
        category=SystemCatalogCategory.OFFICE,
        tags=("数据分析", "报表", "trend"),
        built_in_skill_id="data-analysis",
    ),
    BuiltInSkillEntry(
        slug="doc-review",
        name="文档审阅",
        description="按事实、结构、清晰度和文字四轮审阅文档，输出可执行的修改意见。",
        category=SystemCatalogCategory.OFFICE,
        tags=("审阅", "校对", "review"),
        built_in_skill_id="doc-review",
    ),
    BuiltInSkillEntry(
        slug="research-brief",
        name="调研简报",
        description="检索多来源资料并撰写含引用、分歧与信息缺口的调研简报。",
        category=SystemCatalogCategory.OFFICE,
        tags=("调研", "简报", "research"),
        built_in_skill_id="research-brief",
    ),
    BuiltInSkillEntry(
        slug="long-job-protocol",
        name="长任务协作规范",
        description="把长时间任务拆成计划、执行、复核阶段并留存中间产物。",
        category=SystemCatalogCategory.GENERAL,
        tags=("流程", "长任务"),
        built_in_skill_id="long-job-protocol",
    ),
    BuiltInSkillEntry(
        slug="document-ingest",
        name="文档导入",
        description="把上传的文档解析成可检索、可引用的结构化内容。",
        category=SystemCatalogCategory.GENERAL,
        tags=("导入", "解析"),
        built_in_skill_id="document-ingest",
    ),
    BuiltInSkillEntry(
        slug="company-search",
        name="企业检索",
        description="在已连接的知识库中检索公司与文档信息。",
        category=SystemCatalogCategory.GENERAL,
        tags=("检索", "知识库"),
        built_in_skill_id="company-search",
    ),
    # ── tax ──────────────────────────────────────────────────────────────
    BuiltInSkillEntry(
        slug="tax-compliance",
        name="税务合规风险",
        description="基于已配置的商业数据源评估企业税务合规风险并给出引用。",
        category=SystemCatalogCategory.TAX,
        tags=("合规", "稽查", "风险"),
        built_in_skill_id="tax-compliance",
    ),
    BuiltInSkillEntry(
        slug="tax-policy-trend",
        name="税收政策趋势",
        description="研判税种、行业或地区的政策变化并输出带引用的趋势判断。",
        category=SystemCatalogCategory.TAX,
        tags=("政策", "趋势", "公告"),
        built_in_skill_id="tax-policy-trend",
    ),
    BuiltInSkillEntry(
        slug="tax-invoice-compliance",
        name="发票合规审查",
        description="审查发票的合规性，识别异常开票与抵扣风险。",
        category=SystemCatalogCategory.TAX,
        tags=("发票", "进项", "合规"),
        built_in_skill_id="tax-invoice-compliance",
    ),
    BuiltInSkillEntry(
        slug="tax-recon-supplier",
        name="供应商对账",
        description="核对供应商往来明细，定位并解释差异。",
        category=SystemCatalogCategory.TAX,
        tags=("对账", "往来", "供应商"),
        built_in_skill_id="tax-recon-supplier",
    ),
    BuiltInSkillEntry(
        slug="tax-bank-ledger",
        name="银行流水核对",
        description="核对银行流水与账面记录，输出未达账项清单。",
        category=SystemCatalogCategory.TAX,
        tags=("银行", "流水", "对账"),
        built_in_skill_id="tax-bank-ledger",
    ),
    BuiltInSkillEntry(
        slug="tax-expense-rollup",
        name="费用归集",
        description="按科目与部门归集费用，识别归类异常。",
        category=SystemCatalogCategory.TAX,
        tags=("费用", "归集"),
        built_in_skill_id="tax-expense-rollup",
    ),
    BuiltInSkillEntry(
        slug="tax-opex-variance",
        name="费用波动分析",
        description="分析期间费用波动，定位主要变动科目与原因。",
        category=SystemCatalogCategory.TAX,
        tags=("费用", "波动", "分析"),
        built_in_skill_id="tax-opex-variance",
    ),
    BuiltInSkillEntry(
        slug="tax-ar-risk",
        name="应收账款风险",
        description="评估应收账款账龄与回收风险，提出跟进建议。",
        category=SystemCatalogCategory.TAX,
        tags=("应收", "账龄", "风险"),
        built_in_skill_id="tax-ar-risk",
    ),
    BuiltInSkillEntry(
        slug="tax-financial-statement",
        name="财务报表分析",
        description="联动分析资产负债表、利润表与现金流量表，解释指标变动的驱动因素。",
        category=SystemCatalogCategory.TAX,
        tags=("财务报表", "三表", "比率"),
        built_in_skill_id="tax-financial-statement",
    ),
    BuiltInSkillEntry(
        slug="tax-closing-checklist",
        name="月度关账清单",
        description="以清单方式推进月结，跟踪每项任务的负责人、证据与例外。",
        category=SystemCatalogCategory.TAX,
        tags=("关账", "月结", "清单"),
        built_in_skill_id="tax-closing-checklist",
    ),
    # ── biomed ───────────────────────────────────────────────────────────
    BuiltInSkillEntry(
        slug="biomed-initiation",
        name="药物立项评估",
        description="组织多源检索并撰写带引用的药物研发立项报告。",
        category=SystemCatalogCategory.BIOMED,
        tags=("立项", "研发"),
        built_in_skill_id="biomed-initiation",
    ),
    BuiltInSkillEntry(
        slug="biomed-literature",
        name="文献与机制研究",
        description="从文献中梳理靶点、机制与竞争格局并给出引用。",
        category=SystemCatalogCategory.BIOMED,
        tags=("文献", "靶点", "机制"),
        built_in_skill_id="biomed-literature",
    ),
    BuiltInSkillEntry(
        slug="biomed-patent-fto",
        name="专利自由实施",
        description="撰写专利landscape与自由实施风险评估简报。",
        category=SystemCatalogCategory.BIOMED,
        tags=("专利", "FTO"),
        built_in_skill_id="biomed-patent-fto",
    ),
    BuiltInSkillEntry(
        slug="biomed-clinical-intel",
        name="临床管线情报",
        description="梳理适应症下的在研管线与竞品试验设计。",
        category=SystemCatalogCategory.BIOMED,
        tags=("临床", "管线", "试验"),
        built_in_skill_id="biomed-clinical-intel",
    ),
    BuiltInSkillEntry(
        slug="biomed-cmc-quality",
        name="CMC 与质量风险",
        description="从公开标签、指导原则和召回信息评估药学与质量风险。",
        category=SystemCatalogCategory.BIOMED,
        tags=("CMC", "质量"),
        built_in_skill_id="biomed-cmc-quality",
    ),
    BuiltInSkillEntry(
        slug="biomed-regulatory",
        name="注册申报路径",
        description="梳理 NMPA、FDA、EMA 的申报路径与各阶段所需证据。",
        category=SystemCatalogCategory.BIOMED,
        tags=("注册", "申报", "IND"),
        built_in_skill_id="biomed-regulatory",
    ),
    BuiltInSkillEntry(
        slug="biomed-trial-design",
        name="临床试验设计",
        description="审阅或起草试验的人群、终点、对照与统计假设等核心设计要素。",
        category=SystemCatalogCategory.BIOMED,
        tags=("试验设计", "终点", "样本量"),
        built_in_skill_id="biomed-trial-design",
    ),
)


BUILT_IN_REPORT_TEMPLATE_ENTRIES: Final[tuple[BuiltInReportTemplateEntry, ...]] = (
    BuiltInReportTemplateEntry(
        slug="compliance_risk",
        name="合规风险预警",
        description="企业税务合规风险简报结构。",
        category=SystemCatalogCategory.TAX,
        tags=("合规", "风险"),
        body_file="compliance_risk.md",
    ),
    BuiltInReportTemplateEntry(
        slug="policy_trend",
        name="政策趋势研判",
        description="税种、行业或地区的政策趋势简报结构。",
        category=SystemCatalogCategory.TAX,
        tags=("政策", "趋势"),
        body_file="policy_trend.md",
    ),
    BuiltInReportTemplateEntry(
        slug="monthly_close",
        name="月度关账报告",
        description="月结完成情况、例外事项与待办的汇报结构。",
        category=SystemCatalogCategory.TAX,
        tags=("关账", "月结"),
        body_file="monthly_close.md",
    ),
    BuiltInReportTemplateEntry(
        slug="financial_review",
        name="财务报表分析",
        description="三表联动分析与比率解读的报告结构。",
        category=SystemCatalogCategory.TAX,
        tags=("财务报表", "分析"),
        body_file="financial_review.md",
    ),
    BuiltInReportTemplateEntry(
        slug="target_landscape",
        name="靶点文献与竞争格局",
        description="靶点机制与竞争资产的梳理结构。",
        category=SystemCatalogCategory.BIOMED,
        tags=("靶点", "竞争"),
        body_file="target_landscape.md",
    ),
    BuiltInReportTemplateEntry(
        slug="patent_fto",
        name="专利自由实施评估",
        description="专利族、权利要求对照与 FTO 结论的报告结构。",
        category=SystemCatalogCategory.BIOMED,
        tags=("专利", "FTO"),
        body_file="patent_fto.md",
    ),
    BuiltInReportTemplateEntry(
        slug="clinical_pipeline",
        name="临床管线扫描",
        description="适应症下在研管线与试验设计的梳理结构。",
        category=SystemCatalogCategory.BIOMED,
        tags=("临床", "管线"),
        body_file="clinical_pipeline.md",
    ),
    BuiltInReportTemplateEntry(
        slug="cmc_quality",
        name="CMC 与质量风险",
        description="药学与质量风险简报结构。",
        category=SystemCatalogCategory.BIOMED,
        tags=("CMC", "质量"),
        body_file="cmc_quality.md",
    ),
    BuiltInReportTemplateEntry(
        slug="regulatory_pathway",
        name="注册申报路径",
        description="分市场的申报路径、证据要求与沟通节点结构。",
        category=SystemCatalogCategory.BIOMED,
        tags=("注册", "申报"),
        body_file="regulatory_pathway.md",
    ),
    BuiltInReportTemplateEntry(
        slug="research_brief",
        name="调研简报",
        description="通用主题调研的简报结构，含来源与信息缺口。",
        category=SystemCatalogCategory.OFFICE,
        tags=("调研", "简报"),
        body_file="research_brief.md",
    ),
    BuiltInReportTemplateEntry(
        slug="data_analysis_report",
        name="数据分析报告",
        description="数据口径、发现与结论的分析报告结构。",
        category=SystemCatalogCategory.OFFICE,
        tags=("数据", "分析"),
        body_file="data_analysis_report.md",
    ),
    BuiltInReportTemplateEntry(
        slug="meeting_minutes",
        name="会议纪要",
        description="决议、行动项与待定问题的纪要结构。",
        category=SystemCatalogCategory.OFFICE,
        tags=("会议", "纪要"),
        body_file="meeting_minutes.md",
    ),
    BuiltInReportTemplateEntry(
        slug="deck_outline",
        name="演示文稿大纲",
        description="把结论整理成可直接做成幻灯片的页级大纲。",
        category=SystemCatalogCategory.OFFICE,
        tags=("演示", "大纲"),
        body_file="deck_outline.md",
    ),
    BuiltInReportTemplateEntry(
        slug="initiation_report",
        name="药物立项评估",
        description="带引用的药物研发立项报告结构。",
        category=SystemCatalogCategory.BIOMED,
        tags=("立项", "研发"),
        body_file="initiation_report.md",
    ),
    BuiltInReportTemplateEntry(
        slug="supplier_recon",
        name="供应商对账",
        description="应付与发票对齐后的差异报告结构。",
        category=SystemCatalogCategory.TAX,
        tags=("对账", "供应商"),
        body_file="supplier_recon.md",
    ),
    BuiltInReportTemplateEntry(
        slug="bank_ledger",
        name="银行流水核对",
        description="多银行流水归一与余额调节的报告结构。",
        category=SystemCatalogCategory.TAX,
        tags=("银行", "流水"),
        body_file="bank_ledger.md",
    ),
    BuiltInReportTemplateEntry(
        slug="expense_rollup",
        name="费用归集",
        description="按科目与部门归集费用并标出异常的报告结构。",
        category=SystemCatalogCategory.TAX,
        tags=("费用", "归集"),
        body_file="expense_rollup.md",
    ),
    BuiltInReportTemplateEntry(
        slug="invoice_compliance",
        name="发票合规审查",
        description="发票例外事项与抵扣风险的报告结构。",
        category=SystemCatalogCategory.TAX,
        tags=("发票", "合规"),
        body_file="invoice_compliance.md",
    ),
    BuiltInReportTemplateEntry(
        slug="opex_variance",
        name="费用波动分析",
        description="期间费用同比环比与异常科目的报告结构。",
        category=SystemCatalogCategory.TAX,
        tags=("费用", "波动"),
        body_file="opex_variance.md",
    ),
    BuiltInReportTemplateEntry(
        slug="ar_risk",
        name="应收账款风险",
        description="账龄、回收风险与跟进建议的报告结构。",
        category=SystemCatalogCategory.TAX,
        tags=("应收", "风险"),
        body_file="ar_risk.md",
    ),
)


BUILT_IN_SCENARIO_ENTRIES: Final[tuple[BuiltInScenarioEntry, ...]] = (
    # ── tax ──────────────────────────────────────────────────────────────
    BuiltInScenarioEntry(
        slug="tax-compliance-review",
        name="合规风险预警",
        description="核查企业税务合规风险，输出带来源的风险简报。",
        category=SystemCatalogCategory.TAX,
        tags=("合规", "风险"),
        skill_slugs=("tax-compliance", "research-brief", "docx"),
        report_template_slug="compliance_risk",
        playbook_file="tax-compliance-review.yaml",
        adopt_runtime_name="合规风险预警",
    ),
    BuiltInScenarioEntry(
        slug="tax-policy-watch",
        name="政策趋势研判",
        description="跟踪税种与行业政策变化，研判影响与时间线。",
        category=SystemCatalogCategory.TAX,
        tags=("政策", "趋势"),
        skill_slugs=("tax-policy-trend", "research-brief", "docx"),
        report_template_slug="policy_trend",
        playbook_file="tax-policy-watch.yaml",
        adopt_runtime_name="政策趋势研判",
    ),
    BuiltInScenarioEntry(
        slug="tax-monthly-close",
        name="月度关账",
        description="推进月结清单，核对银行与往来，输出例外事项。",
        category=SystemCatalogCategory.TAX,
        tags=("关账", "月结"),
        skill_slugs=(
            "tax-closing-checklist",
            "tax-bank-ledger",
            "tax-recon-supplier",
            "xlsx",
            "docx",
        ),
        report_template_slug="monthly_close",
        playbook_file="tax-monthly-close.yaml",
    ),
    BuiltInScenarioEntry(
        slug="tax-financial-review",
        name="财务报表分析",
        description="联动分析三表并解释关键指标的变动原因。",
        category=SystemCatalogCategory.TAX,
        tags=("财务报表", "分析"),
        skill_slugs=("tax-financial-statement", "data-analysis", "xlsx", "docx"),
        report_template_slug="financial_review",
        playbook_file="tax-financial-review.yaml",
    ),
    BuiltInScenarioEntry(
        slug="tax-invoice-audit",
        name="发票合规扫描",
        description="批量发票必填项与税号税率检查。",
        category=SystemCatalogCategory.TAX,
        tags=("发票", "审查"),
        skill_slugs=(
            "long-job-protocol",
            "document-ingest",
            "tax-invoice-compliance",
            "xlsx",
            "pdf",
            "docx",
        ),
        report_template_slug="invoice_compliance",
        playbook_file="tax-invoice-audit.yaml",
        adopt_runtime_name="发票合规扫描",
    ),
    BuiltInScenarioEntry(
        slug="tax-supplier-reconciliation",
        name="供应商对账",
        description="应付与发票或对账单对齐，输出差异表。",
        category=SystemCatalogCategory.TAX,
        tags=("对账", "供应商"),
        skill_slugs=(
            "long-job-protocol",
            "document-ingest",
            "tax-recon-supplier",
            "xlsx",
            "pdf",
            "docx",
        ),
        report_template_slug="supplier_recon",
        playbook_file="tax-supplier-reconciliation.yaml",
        adopt_runtime_name="供应商对账",
    ),
    BuiltInScenarioEntry(
        slug="tax-bank-rollup",
        name="多银行流水汇总",
        description="多银行流水归一并做余额调节。",
        category=SystemCatalogCategory.TAX,
        tags=("银行", "流水"),
        skill_slugs=(
            "long-job-protocol",
            "document-ingest",
            "tax-bank-ledger",
            "xlsx",
            "docx",
        ),
        report_template_slug="bank_ledger",
        playbook_file="tax-bank-rollup.yaml",
        adopt_runtime_name="多银行流水汇总",
    ),
    BuiltInScenarioEntry(
        slug="tax-expense-rollup-pack",
        name="子公司报销汇总",
        description="按模板抽取报销单并按公司部门透视。",
        category=SystemCatalogCategory.TAX,
        tags=("费用", "归集"),
        skill_slugs=(
            "long-job-protocol",
            "document-ingest",
            "tax-expense-rollup",
            "xlsx",
            "docx",
        ),
        report_template_slug="expense_rollup",
        playbook_file="tax-expense-rollup-pack.yaml",
        adopt_runtime_name="子公司报销汇总",
    ),
    BuiltInScenarioEntry(
        slug="tax-opex-variance-pack",
        name="部门费用波动",
        description="多期费用同比环比与异常科目。",
        category=SystemCatalogCategory.TAX,
        tags=("费用", "波动"),
        skill_slugs=(
            "long-job-protocol",
            "document-ingest",
            "tax-opex-variance",
            "data-analysis",
            "docx",
        ),
        report_template_slug="opex_variance",
        playbook_file="tax-opex-variance-pack.yaml",
        adopt_runtime_name="部门费用波动",
    ),
    BuiltInScenarioEntry(
        slug="tax-ar-risk-pack",
        name="应收高风险客户",
        description="账龄、回款与外部征信汇总。",
        category=SystemCatalogCategory.TAX,
        tags=("应收", "风险"),
        skill_slugs=("long-job-protocol", "document-ingest", "tax-ar-risk", "docx"),
        report_template_slug="ar_risk",
        playbook_file="tax-ar-risk-pack.yaml",
        adopt_runtime_name="应收高风险客户",
    ),
    # ── biomed ───────────────────────────────────────────────────────────
    BuiltInScenarioEntry(
        slug="biomed-program-initiation",
        name="医药立项报告",
        description="跨文献、临床、专利与 CMC 的立项作业。",
        category=SystemCatalogCategory.BIOMED,
        tags=("立项", "研发"),
        skill_slugs=(
            "long-job-protocol",
            "biomed-initiation",
            "biomed-literature",
            "biomed-clinical-intel",
            "biomed-patent-fto",
            "biomed-cmc-quality",
            "docx",
        ),
        report_template_slug="initiation_report",
        playbook_file="biomed-program-initiation.yaml",
        adopt_runtime_name="医药立项报告",
    ),
    BuiltInScenarioEntry(
        slug="biomed-target-landscape",
        name="靶点文献与竞争格局",
        description="从文献和注册披露整理靶点机制与竞争格局。",
        category=SystemCatalogCategory.BIOMED,
        tags=("靶点", "竞争"),
        skill_slugs=("biomed-literature", "biomed-clinical-intel", "docx"),
        report_template_slug="target_landscape",
        playbook_file="biomed-target-landscape.yaml",
        adopt_runtime_name="靶点文献与竞争格局",
    ),
    BuiltInScenarioEntry(
        slug="biomed-patent-fto-review",
        name="专利自由实施评估",
        description="组合专利检索与文献，评估自由实施风险。",
        category=SystemCatalogCategory.BIOMED,
        tags=("专利", "FTO"),
        skill_slugs=("biomed-patent-fto", "biomed-literature", "docx"),
        report_template_slug="patent_fto",
        playbook_file="biomed-patent-fto-review.yaml",
        adopt_runtime_name="专利自由实施评估",
    ),
    BuiltInScenarioEntry(
        slug="biomed-clinical-scan",
        name="临床管线扫描",
        description="扫描适应症竞品试验与管线设计。",
        category=SystemCatalogCategory.BIOMED,
        tags=("临床", "管线"),
        skill_slugs=("biomed-clinical-intel", "biomed-trial-design", "docx"),
        report_template_slug="clinical_pipeline",
        playbook_file="biomed-clinical-scan.yaml",
        adopt_runtime_name="临床管线扫描",
    ),
    BuiltInScenarioEntry(
        slug="biomed-cmc-review",
        name="CMC 与质量风险简报",
        description="从公开标签、指导原则和召回信息评估药学与质量风险。",
        category=SystemCatalogCategory.BIOMED,
        tags=("CMC", "质量"),
        skill_slugs=("biomed-cmc-quality", "biomed-literature", "docx"),
        report_template_slug="cmc_quality",
        playbook_file="biomed-cmc-review.yaml",
        adopt_runtime_name="CMC 与质量风险简报",
    ),
    BuiltInScenarioEntry(
        slug="biomed-regulatory-path",
        name="注册申报路径",
        description="梳理各市场申报路径与证据要求，识别缺口。",
        category=SystemCatalogCategory.BIOMED,
        tags=("注册", "申报"),
        skill_slugs=("biomed-regulatory", "biomed-cmc-quality", "research-brief", "docx"),
        report_template_slug="regulatory_pathway",
        playbook_file="biomed-regulatory-path.yaml",
    ),
    # ── general office ───────────────────────────────────────────────────
    BuiltInScenarioEntry(
        slug="office-research-report",
        name="主题调研报告",
        description="检索资料并产出带引用的调研报告，可导出为文档。",
        category=SystemCatalogCategory.OFFICE,
        tags=("调研", "报告"),
        skill_slugs=("research-brief", "docx", "doc-review"),
        report_template_slug="research_brief",
        playbook_file="office-research-report.yaml",
    ),
    BuiltInScenarioEntry(
        slug="office-data-report",
        name="数据分析报告",
        description="分析表格数据并产出含图表的分析报告。",
        category=SystemCatalogCategory.OFFICE,
        tags=("数据", "报告"),
        skill_slugs=("data-analysis", "xlsx", "docx"),
        report_template_slug="data_analysis_report",
        playbook_file="office-data-report.yaml",
    ),
    BuiltInScenarioEntry(
        slug="office-deck-building",
        name="演示文稿制作",
        description="把调研或分析结果整理成演示文稿。",
        category=SystemCatalogCategory.OFFICE,
        tags=("演示", "PPT"),
        skill_slugs=("pptx", "research-brief", "data-analysis", "docx"),
        report_template_slug="deck_outline",
        playbook_file="office-deck-building.yaml",
    ),
    BuiltInScenarioEntry(
        slug="office-meeting-followup",
        name="会议纪要与跟进",
        description="把会议记录整理成纪要与行动项，并导出文档。",
        category=SystemCatalogCategory.OFFICE,
        tags=("会议", "纪要"),
        skill_slugs=("meeting-notes", "docx"),
        report_template_slug="meeting_minutes",
        playbook_file="office-meeting-followup.yaml",
    ),
)
