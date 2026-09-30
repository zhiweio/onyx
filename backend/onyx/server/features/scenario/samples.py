"""Sample scenario rule sets for vertical onboarding.

These constants are the reference binding layout for the finance-tax-risk
vertical: admins create SystemScenario entries from them (or the UI offers
them as templates). They document the full shape: playbook phases,
per-phase bindings, runtime policy and delivery actions.
"""

from __future__ import annotations

from typing import Any

FINANCE_TAX_RISK_SCENARIO_SLUG = "finance-tax-risk-report"

FINANCE_TAX_RISK_RULES: dict[str, Any] = {
    "domain": "finance-tax-risk",
    "objective": (
        "对企业财务数据执行税务风险扫描：取数、计算风险指标、按风险框架"
        "比对、交叉验证、生成报告。"
    ),
    "required_inputs": ["企业名称或统一社会信用代码", "最近年度财务报表"],
    "phases": [
        {
            "id": "ingest",
            "done_when": "财税数据与制度文件已检索齐备并落盘 workspace",
            "bindings": {
                "skills": ["finance-tax-risk-report"],
                "document_sets": ["财务制度", "税务政策"],
                "web_search": True,
            },
        },
        {
            "id": "compute",
            "done_when": "风险指标计算完成（compute_metrics.py 输出 JSON）",
            "bindings": {
                "skills": ["finance-tax-risk-report"],
                "web_search": False,
            },
        },
        {
            "id": "validate",
            "done_when": "交叉验证清单全部核对，异常项已标注",
            "bindings": {
                "skills": ["finance-tax-risk-report"],
                "document_sets": ["财务制度"],
                "web_search": True,
            },
        },
        {
            "id": "report",
            "done_when": "风险报告 DOCX 已生成到 outputs/",
            "bindings": {
                "skills": ["finance-tax-risk-report"],
                "gate": "approve_delivery",
                "web_search": False,
            },
        },
    ],
    "deliverables": ["outputs/税务风险报告.docx", "outputs/风险指标.json"],
    "quality_gates": ["指标口径与 metrics-handbook 一致", "每个风险项必须有证据引用"],
    "refusal_rules": ["不得编造财务数据", "缺输入时先提问而非假设"],
    "runtime": {
        "runtime": "opencode",
        "model": "glm-4.7",
        "bindings": {
            "skills": ["finance-tax-risk-report"],
            "mcp_server_ids": [],
            "document_sets": ["财务制度", "税务政策"],
            "web_search": True,
            "gate": "approve_delivery",
        },
        "delivery_actions": ["save_artifacts"],
    },
}
