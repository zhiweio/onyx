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
    # Contract-style templates: YAML files under ``report_templates/`` holding
    # the structured content contract and the render theme. When
    # ``contract_file`` is set, the attached Word asset is the rendered sample
    # document (style reference), not a fill-in skeleton.
    contract_file: str | None = None
    theme_file: str | None = None

    def read_body(self) -> str:
        path = _REPORT_TEMPLATE_DIR / self.body_file
        if not path.is_file():
            raise ValueError(f"Missing report template body: {self.body_file}")
        return path.read_text(encoding="utf-8").strip()

    def builder_slug(self) -> str:
        return self.builder or self.slug

    def read_contract(self) -> dict:
        return _read_template_yaml(self.contract_file)

    def read_theme(self) -> dict:
        return _read_template_yaml(self.theme_file)

    @property
    def is_contract_style(self) -> bool:
        return self.contract_file is not None


def _read_template_yaml(filename: str | None) -> dict:
    if filename is None:
        return {}
    path = _REPORT_TEMPLATE_DIR / filename
    if not path.is_file():
        raise ValueError(f"Missing report template file: {filename}")
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    return loaded if isinstance(loaded, dict) else {}


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
        slug="slideblocks",
        name="Slidev 演示文稿",
        description=(
            "从需求与散装材料（财报、政策文件、PDF、网页、表格）自主产出"
            "设计完整的 Slidev 演示文稿与离线 offline.html，适合汇报、宣讲与路演；"
            "交付格式为 Slidev 源码与网页演示，不生成 .pptx 文件。"
        ),
        category=SystemCatalogCategory.DOCUMENT,
        tags=("slidev", "ppt", "演示文稿"),
        built_in_skill_id="slideblocks",
    ),
    BuiltInSkillEntry(
        slug="vivid-figures-skill",
        name="生动数据图",
        description=(
            "140 个完整配方的科研级绘图技能：按数据与表达目的检索候选模板、"
            "看实图选型、保真复用配方源码，覆盖数据图、统计与机器学习图、"
            "技术图与组合图；数据类图表优先使用本技能。"
        ),
        category=SystemCatalogCategory.GRAPHIC,
        tags=("图表", "画图", "科研绘图"),
        built_in_skill_id="vivid-figures-skill",
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
    BuiltInSkillEntry(
        slug="finance-tax-risk-report",
        name="财税与经营风险分析报告",
        description=(
            "撰写五年期财税与经营风险分析报告：KPI看板、三表五年透视、税负与现金流"
            "专项、TX/OP 风险矩阵与评分、四维建议与整改清单，产出正式 Word 报告。"
        ),
        category=SystemCatalogCategory.REPORT,
        tags=("finance", "tax", "risk", "report"),
        built_in_skill_id="finance-tax-risk-report",
    ),
    BuiltInSkillEntry(
        slug="tax-policy-verify",
        name="政策核验",
        description=(
            "中国大陆财税政策核验模块：官方来源阶梯、所属期适用规则、地区口径"
            "核验、证据卡与时效检查，附中国政府网与税务总局站内检索脚本，供政策"
            "问答、申报底稿与合规体检复用。"
        ),
        category=SystemCatalogCategory.TAX,
        tags=("tax", "policy", "verify"),
        built_in_skill_id="tax-policy-verify",
    ),
    BuiltInSkillEntry(
        slug="caishui-skill",
        name="财税申报与报表",
        description=(
            "中国大陆申报与财务报表工作流：纳税人画像、账单发票银行流水归档"
            "勾稽、试算平衡、资产负债表与利润表底稿、增值税/所得税等申报底稿"
            "与提交前检查清单；政策核验遵循 tax-policy-verify。"
        ),
        category=SystemCatalogCategory.TAX,
        tags=("tax", "filing", "statements", "workflow"),
        built_in_skill_id="caishui-skill",
    ),
    BuiltInSkillEntry(
        slug="tax-tax-audit",
        name="税务审计指引",
        description=(
            "企业财税合规审计与税务审计：审计准则1142号落地、税务内控测试与"
            "穿行测试、涉税舞弊红旗识别、关键审计事项税务披露、监管风险提示"
            "税务维度，按六步闭环组织工作，支持税务合规体检。"
        ),
        category=SystemCatalogCategory.TAX,
        tags=("tax", "audit", "compliance"),
        built_in_skill_id="tax-tax-audit",
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
        description="临床期立项深度调研的契约式模板:决策因子打分、证据表与发现清单。",
        category=SystemCatalogCategory.BIOMED,
        tags=("biomed", "initiation"),
        body_file="initiation_report.md",
        contract_file="initiation_report.contract.yaml",
    ),
    BuiltInReportTemplateEntry(
        slug="listed_company_audit",
        name="上市公司财务审计报告",
        description="覆盖主体、财务、信用、行业与知识产权的契约式审计报告模板。",
        category=SystemCatalogCategory.GENERAL,
        tags=("listed", "audit"),
        body_file="listed_company_audit.md",
        contract_file="listed_company_audit.contract.yaml",
    ),
    BuiltInReportTemplateEntry(
        slug="finance_tax_risk_report",
        name="财税与经营风险分析报告",
        description="五年期财税与经营风险诊断的契约式模板：必答问题、必备产物与软脊柱，版式由主题渲染。",
        category=SystemCatalogCategory.REPORT,
        tags=("finance", "tax", "risk"),
        body_file="finance_tax_risk_report.md",
        contract_file="finance_tax_risk_report.contract.yaml",
        theme_file="finance_tax_risk_report.theme.yaml",
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
    BuiltInScenarioEntry(
        slug="finance-tax-risk-report",
        name="财税与经营风险分析",
        description=(
            "以五年年报为证据，建数、识险、评分成矩阵，并成稿带图表的正式风险报告。"
        ),
        category=SystemCatalogCategory.GENERAL,
        tags=("listed", "finance", "tax", "risk"),
        skill_slugs=(
            "listed-co-entity-resolve",
            "finance-tax-risk-report",
            "hithink-finance",
            "qichacha",
            "zhihuiya",
            "listed-co-industry-context",
            "vivid-figures-skill",
            "chart-gen",
            "docx",
        ),
        report_template_slug="finance_tax_risk_report",
        playbook_file="finance-tax-risk-report.yaml",
    ),
    BuiltInScenarioEntry(
        slug="tax-monthly-review-deck",
        name="月度经营财税汇报",
        description=(
            "以月度三表与费用明细为证据，归因异动、看税负与现金流，"
            "产出管理层月度汇报演示文稿（Slidev + offline.html）。"
        ),
        category=SystemCatalogCategory.TAX,
        tags=("tax", "finance", "monthly", "deck"),
        skill_slugs=(
            "document-ingest",
            "xlsx",
            "vivid-figures-skill",
            "slideblocks",
        ),
        playbook_file="tax-monthly-review-deck.yaml",
    ),
    BuiltInScenarioEntry(
        slug="tax-policy-briefing-deck",
        name="财税新政解读宣讲",
        description=(
            "以官方公告原文为证据，梳理变化要点、前后对照、影响对象与应对时限，"
            "产出面向业务团队或客户的政策解读宣讲演示。"
        ),
        category=SystemCatalogCategory.TAX,
        tags=("tax", "policy", "briefing", "deck"),
        skill_slugs=(
            "document-ingest",
            "vivid-figures-skill",
            "slideblocks",
        ),
        playbook_file="tax-policy-briefing-deck.yaml",
    ),
    BuiltInScenarioEntry(
        slug="tax-risk-review-deck",
        name="税务风险健康检查汇报",
        description=(
            "复用 TX/OP 风险框架体检企业财税与经营风险，"
            "产出带风险矩阵与整改路线的管理层汇报演示（Word 报告版的姊妹场景）。"
        ),
        category=SystemCatalogCategory.TAX,
        tags=("tax", "risk", "review", "deck"),
        skill_slugs=(
            "listed-co-entity-resolve",
            "finance-tax-risk-report",
            "hithink-finance",
            "qichacha",
            "vivid-figures-skill",
            "slideblocks",
        ),
        playbook_file="tax-risk-review-deck.yaml",
    ),
    BuiltInScenarioEntry(
        slug="tax-annual-settlement-deck",
        name="汇算清缴专项汇报",
        description=(
            "梳理纳税调整事项与政策依据，测算应纳税所得额与补退税，"
            "产出带申报前检查清单的汇算清缴专项汇报演示。"
        ),
        category=SystemCatalogCategory.TAX,
        tags=("tax", "settlement", "annual", "deck"),
        skill_slugs=(
            "document-ingest",
            "xlsx",
            "vivid-figures-skill",
            "slideblocks",
        ),
        playbook_file="tax-annual-settlement-deck.yaml",
    ),
    BuiltInScenarioEntry(
        slug="tax-compliance-check",
        name="税务合规体检",
        description=(
            "按审计视角体检企业税务合规：申报一致性、税负合理性、内控有效性、"
            "舞弊红旗与优惠备案五块评级，产出带整改清单的 Word 体检报告。"
        ),
        category=SystemCatalogCategory.TAX,
        tags=("tax", "audit", "compliance", "report"),
        skill_slugs=(
            "tax-tax-audit",
            "tax-policy-verify",
            "qichacha",
            "hithink-finance",
            "vivid-figures-skill",
            "chart-gen",
            "docx",
        ),
        playbook_file="tax-compliance-check.yaml",
    ),
    BuiltInScenarioEntry(
        slug="tax-vat-filing-workpaper",
        name="增值税申报底稿",
        description=(
            "以发票台账与账簿为证据做进销项勾稽与税额桥接，核验适用税率与"
            "优惠口径，产出申报底稿、填报值草稿与提交前检查清单，不代操作"
            "电子税务局。"
        ),
        category=SystemCatalogCategory.TAX,
        tags=("tax", "vat", "filing", "workpaper"),
        skill_slugs=(
            "caishui-skill",
            "tax-policy-verify",
            "xlsx",
        ),
        playbook_file="tax-vat-filing-workpaper.yaml",
    ),
)
