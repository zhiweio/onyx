"""Themed markdown → DOCX rendering for contract-style report templates.

One canonical renderer lives in ``onyx.server.features.build.session.md_to_docx``
(the same engine the session export uses). This module is the report-template
entry point: it resolves a template's contract + theme from their JSONB
columns and renders, and it builds the sample document ("样张") that sync
attaches to a builtin contract template.
"""

from __future__ import annotations

from onyx.report_templates.contract import (
    ALL_COMPONENTS,
    ELEMENT_LABELS,
    ReportContract,
    parse_contract,
    parse_theme,
)
from onyx.server.features.build.session.md_images import ImageLoader
from onyx.server.features.build.session.md_to_docx import markdown_to_docx_bytes


def render_report_docx(
    md_text: str,
    *,
    contract_raw: dict | None = None,
    theme_raw: dict | None = None,
    image_loader: ImageLoader | None = None,
) -> bytes:
    """Render a contract-style report.

    ``contract_raw`` / ``theme_raw`` are the JSONB column payloads. An empty
    contract still renders (the contract then only supplies defaults), so
    callers can render before validation with identical output.
    """
    contract = parse_contract(contract_raw)
    theme = parse_theme(theme_raw)
    return markdown_to_docx_bytes(
        md_text,
        image_loader=image_loader,
        theme=theme,
        include_toc=contract.require_toc,
    )


def build_sample_markdown(contract: ReportContract) -> str:
    """Build the sample-document markdown for a contract template.

    The sample is a style reference, not a fill-in skeleton: it shows the
    cover metadata, every component in the vocabulary with example data, and
    the contract's requirements so an agent (or admin) can see what the
    rendered report will look like.
    """
    components = [
        component
        for component in ALL_COMPONENTS
        if not contract.components or component in contract.components
    ]
    lines: list[str] = [
        "---",
        'title: "{{公司名称}}"',
        'subtitle: "{{报告主标题,如 2021—2025 年度财税与经营风险分析}}"',
        'kicker: "机构级研究报告"',
        'org: "{{证券代码 | 交易所}}"',
        'data_cutoff: "数据基准日: {{YYYY-MM-DD}}"',
        'date: "编制日期: {{YYYY 年 MM 月}}"',
        'disclaimer: "本报告基于公开披露信息编制,不构成投资建议。"',
        "---",
        "",
    ]
    if "toc" in components:
        lines += [
            "(本模板渲染时自动在封面后插入目录域,此处不占章节。)",
            "",
        ]

    lines += ["# 一、组件样例(报告说明章)", ""]
    lines += [
        "本章展示渲染器支持的组件。写报告时按模板正文的契约自由组排章节,",
        "组件按需选用,数量与顺序由证据决定。",
        "",
    ]

    if "kpi" in components:
        lines += [
            "## KPI 指标条",
            "",
            "```kpi",
            "营业收入 | 4.73 亿元 | 关注",
            "归母净利润 | 0.90 亿元 | 改善",
            "毛利率 | 35.6% | 稳健",
            "净现比 | 0.48 | 预警",
            "```",
            "",
        ]

    if "callout" in components:
        lines += [
            "## 提示框",
            "",
            "> [!风险] 高新技术资格复审",
            "> 证书有效期覆盖 2023—2025 年,2026 年起需重新通过复审。",
            "",
            "> [!洞察] 现金流转弱",
            "> 净现比 2025 年降至 0.48,低于 0.5 警戒线。",
            "",
            "> [!提示] 口径说明",
            "> 2023 年营业成本重分类,比较时已标注不可直接横比。",
            "",
        ]

    if "table" in components:
        lines += [
            "## 数据表",
            "",
            "| 指标 | 2021 | 2023 | 2025 |",
            "| --- | --- | --- | --- |",
            "| 毛利率 (%) | 46.1 | 37.9 | 35.6 |",
            "| 净利率 (%) | 27.1 | 12.1 | 16.6 |",
            "",
            "来源: 公司各年年度报告(第 X 页)。表格下方写来源行,每个数字可溯源。",
            "",
        ]

    if "figure" in components:
        lines += [
            "## 图表",
            "",
            "![图 1 营业收入与归母净利润五年趋势](outputs/charts/example.png)",
            "",
            "图表由 vivid-figures-skill / chart-gen 产出 PNG 后按路径嵌入,",
            f"本模板要求全篇不少于 {max(contract.min_figures, 1)} 张。",
            "",
        ]

    lines += ["# 二、契约要求(不渲染为正文,交付前删除本段)", ""]
    if contract.must_answer:
        lines += ["**必答问题**:", ""]
        lines += [
            f"{index}. {item}" for index, item in enumerate(contract.must_answer, 1)
        ]
        lines += [""]
    if contract.required_elements:
        lines += [
            "**必备产物**: "
            + "、".join(
                ELEMENT_LABELS.get(element, element)
                for element in contract.required_elements
            ),
            "",
        ]
    if contract.spine:
        lines += ["**叙事脊柱**: " + " → ".join(contract.spine), ""]
    if contract.hard_rules:
        lines += ["**硬规则**:", ""]
        lines += [f"- {rule}" for rule in contract.hard_rules]
        lines += [""]

    if contract.require_disclaimer:
        lines += [
            "# 三、免责声明",
            "",
            "本报告基于公司公开披露的年度财务报告及相关公告编制,为分析框架,",
            "不构成投资建议、税务申报意见或审计意见。",
            "",
        ]
    return "\n".join(lines)


def build_sample_docx(
    contract_raw: dict | None,
    theme_raw: dict | None,
) -> bytes:
    """Render the sample document for a builtin contract template."""
    contract = parse_contract(contract_raw)
    return render_report_docx(
        build_sample_markdown(contract),
        contract_raw=contract_raw,
        theme_raw=theme_raw,
    )
