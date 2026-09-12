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
from onyx.skills.kimi_official import KIMI_OFFICIAL_SKILLS
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
        tags=("pdf", "文档"),
        built_in_skill_id="pdf",
    ),
    BuiltInSkillEntry(
        slug="document-ingest",
        name="文档导入",
        description="把上传的文档解析成可检索、可引用的结构化内容。",
        category=SystemCatalogCategory.DOCUMENT,
        tags=("ingest", "文档"),
        built_in_skill_id="document-ingest",
    ),
    # ── biomedical ───────────────────────────────────────────────────────
    BuiltInSkillEntry(
        slug="biomed-literature",
        name="文献与机制研究",
        description="从文献中梳理靶点、机制与竞争格局并给出引用。",
        category=SystemCatalogCategory.BIOMED,
        tags=("literature", "pubmed"),
        built_in_skill_id="biomed-literature",
    ),
    BuiltInSkillEntry(
        slug="biomed-patent-fto",
        name="专利自由实施",
        description="撰写专利landscape与自由实施风险评估简报。",
        category=SystemCatalogCategory.BIOMED,
        tags=("patent", "fto"),
        built_in_skill_id="biomed-patent-fto",
    ),
    BuiltInSkillEntry(
        slug="biomed-clinical-intel",
        name="临床管线情报",
        description="梳理适应症下的在研管线与竞品试验设计。",
        category=SystemCatalogCategory.BIOMED,
        tags=("clinical", "trial"),
        built_in_skill_id="biomed-clinical-intel",
    ),
    BuiltInSkillEntry(
        slug="biomed-regulatory",
        name="注册申报路径",
        description="梳理 NMPA、FDA、EMA 的申报路径与各阶段所需证据。",
        category=SystemCatalogCategory.BIOMED,
        tags=("regulatory", "nda"),
        built_in_skill_id="biomed-regulatory",
    ),
    BuiltInSkillEntry(
        slug="biomed-clinical-initiation",
        name="临床期立项深度调研",
        description="基于公开检索与用户文件，撰写含患者池、PoS、注册路径、销售双情景与 Go/No-Go 的临床期立项报告。",
        category=SystemCatalogCategory.BIOMED,
        tags=("initiation", "clinical"),
        built_in_skill_id="biomed-clinical-initiation",
    ),
    # ── listed-company audit ─────────────────────────────────────────────
    BuiltInSkillEntry(
        slug="hithink-finance",
        name="同花顺财务查询",
        description=(
            "查询 A 股上市公司财务、估值与行情数据。"
            "覆盖利润表、资产负债表、现金流量表、关键指标、估值与行情。"
        ),
        category=SystemCatalogCategory.GENERAL,
        tags=("finance", "listed", "hithink"),
        built_in_skill_id="hithink-finance",
    ),
    BuiltInSkillEntry(
        slug="zhihuiya",
        name="智慧芽专利情报",
        description=(
            "查询全球专利与创新情报。"
            "覆盖专利检索、法律状态、同族、引用、技术功效与公司研发画像。"
        ),
        category=SystemCatalogCategory.GENERAL,
        tags=("patent", "innovation", "zhihuiya"),
        built_in_skill_id="zhihuiya",
    ),
    BuiltInSkillEntry(
        slug="qichacha",
        name="企查查工商合规",
        description=(
            "查询中国企业工商、股权、风险与经营信息。"
            "覆盖主体核验、受益所有人、司法与经营异常。"
        ),
        category=SystemCatalogCategory.GENERAL,
        tags=("kyc", "compliance", "qichacha"),
        built_in_skill_id="qichacha",
    ),
    BuiltInSkillEntry(
        slug="listed-co-entity-resolve",
        name="上市主体解析",
        description="把公司名、证券简称或代码解析为统一的上市主体标识。",
        category=SystemCatalogCategory.GENERAL,
        tags=("listed", "entity"),
        built_in_skill_id="listed-co-entity-resolve",
    ),
    BuiltInSkillEntry(
        slug="listed-co-filings-normalize",
        name="公告与财报归一",
        description="整理年报、半年报与临时公告，抽出可比期间与关键披露。",
        category=SystemCatalogCategory.GENERAL,
        tags=("listed", "filings"),
        built_in_skill_id="listed-co-filings-normalize",
    ),
    BuiltInSkillEntry(
        slug="listed-co-metric-audit",
        name="财务指标审计",
        description="核对利润、资产负债、现金流与关键比率，标出异常波动。",
        category=SystemCatalogCategory.GENERAL,
        tags=("listed", "metrics"),
        built_in_skill_id="listed-co-metric-audit",
    ),
    BuiltInSkillEntry(
        slug="listed-co-credit-legal",
        name="信用与法律风险",
        description="汇总诉讼、处罚、担保与失信记录，评估信用与法律敞口。",
        category=SystemCatalogCategory.GENERAL,
        tags=("listed", "legal"),
        built_in_skill_id="listed-co-credit-legal",
    ),
    BuiltInSkillEntry(
        slug="listed-co-industry-context",
        name="行业与同业对照",
        description="把公司指标放到行业与同业样本中对照。",
        category=SystemCatalogCategory.GENERAL,
        tags=("listed", "industry"),
        built_in_skill_id="listed-co-industry-context",
    ),
    BuiltInSkillEntry(
        slug="listed-co-ip-rd",
        name="知识产权与研发",
        description="盘点专利、软著与研发投入，判断技术资产质量。",
        category=SystemCatalogCategory.GENERAL,
        tags=("listed", "ip"),
        built_in_skill_id="listed-co-ip-rd",
    ),
    BuiltInSkillEntry(
        slug="listed-co-red-blue-review",
        name="红蓝队复核",
        description="对财务与合规结论做对抗复核，标出证据缺口。",
        category=SystemCatalogCategory.GENERAL,
        tags=("listed", "review"),
        built_in_skill_id="listed-co-red-blue-review",
    ),
    BuiltInSkillEntry(
        slug="listed-co-report-compose",
        name="审计报告成稿",
        description="把各技能结论收成上市公司财务审计报告。",
        category=SystemCatalogCategory.GENERAL,
        tags=("listed", "report"),
        built_in_skill_id="listed-co-report-compose",
    ),
    BuiltInSkillEntry(
        slug="contract-review",
        name="合同审查",
        description="审查合同主体、条款风险与履约约束，并对照工商与信用记录。",
        category=SystemCatalogCategory.GENERAL,
        tags=("contract", "legal"),
        built_in_skill_id="contract-review",
    ),
    BuiltInSkillEntry(
        slug="kyb-verification-qcc",
        name="KYB 主体核验",
        description="核验企业登记状态、统一社会信用代码与法定代表人。",
        category=SystemCatalogCategory.GENERAL,
        tags=("qcc", "kyb"),
        built_in_skill_id="kyb-verification-qcc",
    ),
    BuiltInSkillEntry(
        slug="ubo-screening-qcc",
        name="受益所有人筛查",
        description="追溯股权穿透与最终受益人。",
        category=SystemCatalogCategory.GENERAL,
        tags=("qcc", "ubo"),
        built_in_skill_id="ubo-screening-qcc",
    ),
    BuiltInSkillEntry(
        slug="counterparty-risk-qcc",
        name="交易对手风险",
        description="评估交易对手的经营、诉讼与失信风险。",
        category=SystemCatalogCategory.GENERAL,
        tags=("qcc", "risk"),
        built_in_skill_id="counterparty-risk-qcc",
    ),
    BuiltInSkillEntry(
        slug="new-supplier-screening-qcc",
        name="新供应商筛查",
        description="筛查新供应商的主体资格、关联与风险信号。",
        category=SystemCatalogCategory.GENERAL,
        tags=("qcc", "supplier"),
        built_in_skill_id="new-supplier-screening-qcc",
    ),
    BuiltInSkillEntry(
        slug="supplier-annual-check-qcc",
        name="供应商年审",
        description="复核存量供应商当年的登记、诉讼与经营变化。",
        category=SystemCatalogCategory.GENERAL,
        tags=("qcc", "supplier"),
        built_in_skill_id="supplier-annual-check-qcc",
    ),
    BuiltInSkillEntry(
        slug="vendor-assessment-qcc",
        name="供应商评估",
        description="综合工商、经营与风险数据评估供应商质量。",
        category=SystemCatalogCategory.GENERAL,
        tags=("qcc", "vendor"),
        built_in_skill_id="vendor-assessment-qcc",
    ),
    BuiltInSkillEntry(
        slug="credit-due-diligence-qcc",
        name="信用尽调",
        description="汇总工商、司法与经营异常，形成信用尽调结论。",
        category=SystemCatalogCategory.GENERAL,
        tags=("qcc", "credit"),
        built_in_skill_id="credit-due-diligence-qcc",
    ),
    BuiltInSkillEntry(
        slug="credit-monitoring-qcc",
        name="信用监控",
        description="跟踪企业信用与风险事件变化。",
        category=SystemCatalogCategory.GENERAL,
        tags=("qcc", "monitor"),
        built_in_skill_id="credit-monitoring-qcc",
    ),
    BuiltInSkillEntry(
        slug="ic-memo-qcc",
        name="投委会备忘",
        description="整理工商、股权与风险材料，起草投委会备忘。",
        category=SystemCatalogCategory.GENERAL,
        tags=("qcc", "ic"),
        built_in_skill_id="ic-memo-qcc",
    ),
    BuiltInSkillEntry(
        slug="equity-structure-qcc",
        name="股权结构",
        description="梳理股东、穿透与关联企业。",
        category=SystemCatalogCategory.GENERAL,
        tags=("qcc", "equity"),
        built_in_skill_id="equity-structure-qcc",
    ),
    BuiltInSkillEntry(
        slug="history-evolution-qcc",
        name="沿革梳理",
        description="还原企业名称、股东与经营范围沿革。",
        category=SystemCatalogCategory.GENERAL,
        tags=("qcc", "history"),
        built_in_skill_id="history-evolution-qcc",
    ),
    BuiltInSkillEntry(
        slug="executive-background-qcc",
        name="高管背景",
        description="核验法定代表人与高管任职、关联与限制。",
        category=SystemCatalogCategory.GENERAL,
        tags=("qcc", "executive"),
        built_in_skill_id="executive-background-qcc",
    ),
    BuiltInSkillEntry(
        slug="litigation-analysis-qcc",
        name="诉讼分析",
        description="归纳司法案件类型、角色与金额。",
        category=SystemCatalogCategory.GENERAL,
        tags=("qcc", "litigation"),
        built_in_skill_id="litigation-analysis-qcc",
    ),
    BuiltInSkillEntry(
        slug="bankruptcy-monitor-qcc",
        name="破产监控",
        description="检查破产重整、清算与失信被执行记录。",
        category=SystemCatalogCategory.GENERAL,
        tags=("qcc", "bankruptcy"),
        built_in_skill_id="bankruptcy-monitor-qcc",
    ),
    BuiltInSkillEntry(
        slug="guarantor-check-qcc",
        name="担保人核查",
        description="核查担保人主体资格与对外担保风险。",
        category=SystemCatalogCategory.GENERAL,
        tags=("qcc", "guarantor"),
        built_in_skill_id="guarantor-check-qcc",
    ),
    BuiltInSkillEntry(
        slug="debt-recovery-assessment-qcc",
        name="清收评估",
        description="评估债务人资产、诉讼与可执行性。",
        category=SystemCatalogCategory.GENERAL,
        tags=("qcc", "debt"),
        built_in_skill_id="debt-recovery-assessment-qcc",
    ),
    BuiltInSkillEntry(
        slug="trade-finance-compliance-qcc",
        name="贸易融资合规",
        description="核验贸易对手主体与经营异常，服务融资合规。",
        category=SystemCatalogCategory.GENERAL,
        tags=("qcc", "trade"),
        built_in_skill_id="trade-finance-compliance-qcc",
    ),
    BuiltInSkillEntry(
        slug="contract-party-check-qcc",
        name="合同相对方核查",
        description="核验合同相对方登记、授权与履约风险。",
        category=SystemCatalogCategory.GENERAL,
        tags=("qcc", "contract"),
        built_in_skill_id="contract-party-check-qcc",
    ),
    BuiltInSkillEntry(
        slug="labor-compliance-qcc",
        name="用工合规",
        description="检查社保、劳动仲裁与用工相关风险。",
        category=SystemCatalogCategory.GENERAL,
        tags=("qcc", "labor"),
        built_in_skill_id="labor-compliance-qcc",
    ),
    BuiltInSkillEntry(
        slug="license-validation-qcc",
        name="证照核验",
        description="核验行政许可、资质与有效期。",
        category=SystemCatalogCategory.GENERAL,
        tags=("qcc", "license"),
        built_in_skill_id="license-validation-qcc",
    ),
    BuiltInSkillEntry(
        slug="ip-asset-inventory-qcc",
        name="知识产权盘点",
        description="盘点商标、专利与软著权属。",
        category=SystemCatalogCategory.GENERAL,
        tags=("qcc", "ip"),
        built_in_skill_id="ip-asset-inventory-qcc",
    ),
    BuiltInSkillEntry(
        slug="ip-infringement-alert-qcc",
        name="侵权预警",
        description="跟踪知识产权纠纷与侵权风险。",
        category=SystemCatalogCategory.GENERAL,
        tags=("qcc", "ip"),
        built_in_skill_id="ip-infringement-alert-qcc",
    ),
    BuiltInSkillEntry(
        slug="fundraising-tracker-qcc",
        name="融资追踪",
        description="整理对外投资、融资事件与股东变化。",
        category=SystemCatalogCategory.GENERAL,
        tags=("qcc", "fundraising"),
        built_in_skill_id="fundraising-tracker-qcc",
    ),
    BuiltInSkillEntry(
        slug="strip-profile-qcc",
        name="企业画像",
        description="汇总工商、经营与风险，形成一页企业画像。",
        category=SystemCatalogCategory.GENERAL,
        tags=("qcc", "profile"),
        built_in_skill_id="strip-profile-qcc",
    ),
    BuiltInSkillEntry(
        slug="business-health-scan-qcc",
        name="经营健康扫描",
        description="扫描经营异常、行政处罚与存续风险。",
        category=SystemCatalogCategory.GENERAL,
        tags=("qcc", "health"),
        built_in_skill_id="business-health-scan-qcc",
    ),
    BuiltInSkillEntry(
        slug="competitor-analysis-qcc",
        name="竞争对照",
        description="对照同业主体的登记、规模与风险信号。",
        category=SystemCatalogCategory.GENERAL,
        tags=("qcc", "competitor"),
        built_in_skill_id="competitor-analysis-qcc",
    ),
    BuiltInSkillEntry(
        slug="financial-report-analysis",
        name="财报解读",
        description=(
            "解读最新季报年报：三表同比环比、异常检测、季度趋势与经营KPI。"
            "支持上传财报，并调用同花顺、企查查、智慧芽与公开检索出图。"
        ),
        category=SystemCatalogCategory.REPORT,
        tags=("finance", "earnings", "report"),
        built_in_skill_id="financial-report-analysis",
    ),
    *(
        BuiltInSkillEntry(
            slug=skill.slug,
            name=skill.name,
            description=skill.description,
            category=skill.category,
            tags=skill.tags,
            built_in_skill_id=skill.slug,
        )
        for skill in KIMI_OFFICIAL_SKILLS
    ),
)


BUILT_IN_REPORT_TEMPLATE_ENTRIES: Final[tuple[BuiltInReportTemplateEntry, ...]] = (
    BuiltInReportTemplateEntry(
        slug="initiation_report",
        name="临床期立项调研报告",
        description="临床期立项深度调研的正式报告骨架。",
        category=SystemCatalogCategory.BIOMED,
        tags=("biomed", "initiation"),
        body_file="initiation_report.md",
    ),
    BuiltInReportTemplateEntry(
        slug="listed_company_audit",
        name="上市公司财务审计报告",
        description="覆盖主体、财务、信用、行业与知识产权的审计报告骨架。",
        category=SystemCatalogCategory.GENERAL,
        tags=("listed", "audit"),
        body_file="listed_company_audit.md",
    ),
)


BUILT_IN_SCENARIO_ENTRIES: Final[tuple[BuiltInScenarioEntry, ...]] = (
    BuiltInScenarioEntry(
        slug="biomed-clinical-initiation",
        name="临床期立项深度调研",
        description="公开数据库与已安装检索工具支撑的临床期立项报告，含患者池、PoS、注册路径与销售双情景。",
        category=SystemCatalogCategory.BIOMED,
        tags=("biomed", "initiation"),
        skill_slugs=(
            "document-ingest",
            "biomed-literature",
            "biomed-patent-fto",
            "biomed-clinical-intel",
            "biomed-regulatory",
            "biomed-clinical-initiation",
            "docx",
        ),
        report_template_slug="initiation_report",
        playbook_file="biomed-clinical-initiation.yaml",
    ),
    BuiltInScenarioEntry(
        slug="listed-company-financial-audit",
        name="上市公司财务审计",
        description=(
            "解析上市主体，核对财报与关键指标，评估信用法律风险，"
            "并对照行业、知识产权后成稿。"
        ),
        category=SystemCatalogCategory.GENERAL,
        tags=("listed", "audit", "finance"),
        skill_slugs=(
            "listed-co-entity-resolve",
            "listed-co-filings-normalize",
            "listed-co-metric-audit",
            "hithink-finance",
            "listed-co-credit-legal",
            "qichacha",
            "listed-co-industry-context",
            "listed-co-ip-rd",
            "zhihuiya",
            "listed-co-red-blue-review",
            "listed-co-report-compose",
            "docx",
        ),
        report_template_slug="listed_company_audit",
        playbook_file="listed-company-financial-audit.yaml",
    ),
)
