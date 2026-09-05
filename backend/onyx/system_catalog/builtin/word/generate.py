"""Build official Word report templates from a per-slug spec.

``generate_official_docx(slug)`` returns the document bytes and the typed
placeholder schema that sync attaches. Names in the file are the source of
truth; the schema only adds kind, description and example.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Final

from docx import Document

from onyx.report_templates.docx_template import extract_docx_placeholder_schema
from onyx.report_templates.placeholders import PlaceholderKind, PlaceholderSpec
from onyx.system_catalog.builtin.word import styles


@dataclass(frozen=True)
class TableColumn:
    header: str
    field: str
    description: str
    example: str = ""


@dataclass(frozen=True)
class ScalarField:
    name: str
    kind: PlaceholderKind
    description: str
    example: str = ""
    heading: str | None = None


@dataclass(frozen=True)
class OfficialWordSpec:
    slug: str
    title: str
    table_heading: str
    table_collection: str
    table_columns: tuple[TableColumn, ...]
    extra_scalars: tuple[ScalarField, ...] = ()
    extra_sections: tuple[tuple[str, str], ...] = ()


_FINDINGS: Final[tuple[TableColumn, ...]] = (
    TableColumn("发现", "title", "一条发现的标题", "进项认证异常"),
    TableColumn("严重程度", "severity", "高 / 中 / 低", "高"),
    TableColumn("金额", "amount", "涉及金额，无金额写 未获取", "120万"),
    TableColumn("责任人", "owner", "跟进责任人", "税务经理"),
    TableColumn("来源", "source", "证据来源或文件名", "增值税申报表"),
)

_EXCEPTIONS: Final[tuple[TableColumn, ...]] = (
    TableColumn("例外", "title", "例外事项标题", "银行未达账"),
    TableColumn("严重程度", "severity", "高 / 中 / 低", "中"),
    TableColumn("金额", "amount", "涉及金额", "35万"),
    TableColumn("责任人", "owner", "跟进责任人", "出纳"),
    TableColumn("来源", "source", "对账文件或模块", "工商银行对账单"),
)

_DIFFERENCES: Final[tuple[TableColumn, ...]] = (
    TableColumn("差异", "title", "差异事项", "发票未入账"),
    TableColumn("严重程度", "severity", "高 / 中 / 低", "中"),
    TableColumn("金额", "amount", "差异金额", "8.2万"),
    TableColumn("责任人", "owner", "跟进责任人", "应付会计"),
    TableColumn("来源", "source", "两侧文件", "供应商对账单"),
)

_ACTIONS: Final[tuple[TableColumn, ...]] = (
    TableColumn("行动项", "title", "具体动作", "补充关账证据"),
    TableColumn("负责人", "owner", "行动项负责人", "财务经理"),
    TableColumn("截止日期", "due", "YYYY-MM-DD，未指定写 未指定", "2026-09-15"),
    TableColumn("状态", "status", "未开始 / 进行中 / 完成", "未开始"),
    TableColumn("备注", "source", "依据或会议决议", "第 3 项决议"),
)

_SLIDES: Final[tuple[TableColumn, ...]] = (
    TableColumn("页", "title", "幻灯片标题", "问题与结论"),
    TableColumn("要点", "severity", "该页要说清的一点", "关账仍被银行未达阻塞"),
    TableColumn("证据", "amount", "支撑数字或来源", "未达 35 万"),
    TableColumn("受众", "owner", "该页主要给谁看", "管理层"),
    TableColumn("备注", "source", "演讲提示", "先结论后细节"),
)


def _spec(
    slug: str,
    title: str,
    *,
    table_heading: str = "发现与例外",
    table_collection: str = "findings",
    table_columns: tuple[TableColumn, ...] = _FINDINGS,
    extra_scalars: tuple[ScalarField, ...] = (),
    extra_sections: tuple[tuple[str, str], ...] = (),
) -> OfficialWordSpec:
    return OfficialWordSpec(
        slug=slug,
        title=title,
        table_heading=table_heading,
        table_collection=table_collection,
        table_columns=table_columns,
        extra_scalars=extra_scalars,
        extra_sections=extra_sections,
    )


OFFICIAL_WORD_SPECS: Final[dict[str, OfficialWordSpec]] = {
    spec.slug: spec
    for spec in (
        _spec("compliance_risk", "合规风险预警报告"),
        _spec("policy_trend", "税收政策趋势研判"),
        _spec(
            "monthly_close",
            "月度关账报告",
            table_heading="例外事项",
            table_collection="exceptions",
            table_columns=_EXCEPTIONS,
        ),
        _spec("financial_review", "财务报表分析报告"),
        _spec("target_landscape", "靶点文献与竞争格局"),
        _spec("patent_fto", "专利自由实施评估"),
        _spec("clinical_pipeline", "临床管线扫描"),
        _spec("cmc_quality", "CMC 与质量风险简报"),
        _spec("regulatory_pathway", "注册申报路径"),
        _spec("research_brief", "调研简报"),
        _spec("data_analysis_report", "数据分析报告"),
        _spec(
            "meeting_minutes",
            "会议纪要",
            table_heading="行动项",
            table_collection="actions",
            table_columns=_ACTIONS,
            extra_scalars=(
                ScalarField(
                    "meeting_title",
                    "text",
                    "会议主题",
                    "9 月关账评审",
                    "会议主题",
                ),
                ScalarField(
                    "attendees",
                    "multiline",
                    "参会人，逗号分隔",
                    "张三, 李四",
                    "参会人",
                ),
            ),
        ),
        _spec("initiation_report", "药物立项评估报告"),
        _spec(
            "supplier_recon",
            "供应商对账报告",
            table_heading="差异清单",
            table_collection="differences",
            table_columns=_DIFFERENCES,
        ),
        _spec(
            "bank_ledger",
            "银行流水核对报告",
            table_heading="未达账项",
            table_collection="differences",
            table_columns=_DIFFERENCES,
        ),
        _spec("expense_rollup", "费用归集报告"),
        _spec(
            "invoice_compliance",
            "发票合规审查报告",
            table_heading="例外清单",
            table_collection="exceptions",
            table_columns=_EXCEPTIONS,
        ),
        _spec("opex_variance", "费用波动分析报告"),
        _spec("ar_risk", "应收账款风险清单"),
        _spec(
            "deck_outline",
            "演示文稿大纲",
            table_heading="幻灯片大纲",
            table_collection="slides",
            table_columns=_SLIDES,
            extra_scalars=(
                ScalarField(
                    "audience",
                    "text",
                    "主要受众",
                    "管理层",
                    "受众",
                ),
                ScalarField(
                    "key_message",
                    "multiline",
                    "一句话结论",
                    "本月不可关账",
                    "关键信息",
                ),
            ),
        ),
    )
}

_CORE_OVERLAY: Final[tuple[PlaceholderSpec, ...]] = (
    PlaceholderSpec(
        name="company_header",
        kind="text",
        required=True,
        description="页眉中的主体或报告线名称",
        example="某某股份有限公司 · 财务部",
    ),
    PlaceholderSpec(
        name="entity_name",
        kind="text",
        required=True,
        description="报告主体的法定名称",
        example="某某股份有限公司",
    ),
    PlaceholderSpec(
        name="period",
        kind="text",
        required=True,
        description="报告期间",
        example="2026年8月",
    ),
    PlaceholderSpec(
        name="currency",
        kind="text",
        required=True,
        description="金额币种",
        example="CNY",
    ),
    PlaceholderSpec(
        name="report_date",
        kind="date",
        required=True,
        description="编制日期",
        example="2026-09-05",
    ),
    PlaceholderSpec(
        name="conclusion",
        kind="multiline",
        required=True,
        description="结论。不可关账或不可签署时写清前置条件",
        example="本月不可关账，银行未达仍未核销。",
    ),
    PlaceholderSpec(
        name="open_issues",
        kind="multiline",
        required=True,
        description="未决问题。无则写 无",
        example="工商银行未达 35 万待回单。",
    ),
    PlaceholderSpec(
        name="data_gaps",
        kind="multiline",
        required=True,
        description="数据缺口。无则写 无",
        example="缺少子公司 B 的费用明细。",
    ),
)


def overlay_for_spec(spec: OfficialWordSpec) -> list[PlaceholderSpec]:
    overlay = list(_CORE_OVERLAY)
    for column in spec.table_columns:
        overlay.append(
            PlaceholderSpec(
                name=f"{spec.table_collection}.{column.field}",
                kind="table",
                required=True,
                description=column.description,
                example=column.example,
            )
        )
    for extra in spec.extra_scalars:
        overlay.append(
            PlaceholderSpec(
                name=extra.name,
                kind=extra.kind,
                required=True,
                description=extra.description,
                example=extra.example,
            )
        )
    return overlay


def build_document(spec: OfficialWordSpec) -> bytes:
    document = Document()
    styles.configure_document(document)
    styles.add_header(document)
    styles.add_footer(document)
    styles.add_title(document, spec.title)
    styles.add_cover_line(document)
    for extra in spec.extra_scalars:
        if extra.heading:
            styles.add_heading(document, extra.heading)
            styles.add_body(document, "{{" + extra.name + "}}")
    for heading, token in spec.extra_sections:
        styles.add_heading(document, heading)
        styles.add_body(document, token)
    styles.add_heading(document, spec.table_heading)
    styles.add_bordered_table(
        document,
        headers=[column.header for column in spec.table_columns],
        prototype_cells=[
            "{{" + spec.table_collection + "." + column.field + "}}"
            for column in spec.table_columns
        ],
    )
    styles.add_closing(document)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def generate_official_docx(slug: str) -> tuple[bytes, list[PlaceholderSpec]]:
    """Return generated bytes and the merged placeholder schema for ``slug``."""
    spec = OFFICIAL_WORD_SPECS.get(slug)
    if spec is None:
        raise KeyError(f"No official Word builder for '{slug}'")
    asset_bytes = build_document(spec)
    schema = extract_docx_placeholder_schema(asset_bytes, overlay_for_spec(spec))
    return asset_bytes, schema


def official_builder_slugs() -> frozenset[str]:
    return frozenset(OFFICIAL_WORD_SPECS)
