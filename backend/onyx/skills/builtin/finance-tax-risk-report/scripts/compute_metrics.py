"""Compute the five-year KPI dashboard for a finance-tax-risk report.

Input is a normalized statements JSON (see ``--sample-statements``): the three
statements aligned on ``years``. Amounts are in 元 unless ``unit`` says
otherwise. Missing subjects stay null and surface as 未获取 in the report —
never filled with zeros. Derived metrics follow
``references/metrics-handbook.md``; do not hand-fill them.

Usage::

    python compute_metrics.py --input statements.json --out kpi_dashboard.json
    python compute_metrics.py --sample > kpi_dashboard.json
    python compute_metrics.py --sample-statements > statements.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Final

Number = int | float | None
Row = dict[str, Any]
YEARS = 5

# ---------------------------------------------------------------- sample data
# 示例数据为某装备制造上市公司风格的五年三表（单位：元），仅用于格式演示与自测。
SAMPLE_STATEMENTS: Final[dict[str, Any]] = {
    "company": "示例集团",
    "unit": "元",
    "years": [2021, 2022, 2023, 2024, 2025],
    "income": {
        "revenue": [4.73e8, 2.91e8, 3.84e8, 3.60e8, 4.34e8],
        "cost": [2.550e8, 1.905e8, 2.382e8, 2.442e8, 2.795e8],
        "selling": [3.71e7, 1.99e7, 3.13e7, 1.48e7, 1.48e7],
        "admin": [3.80e7, 2.50e7, 3.00e7, 2.90e7, 3.30e7],
        "rd": [2.19e7, 1.88e7, 2.23e7, 2.33e7, 2.02e7],
        "finance": [5.0e5, 8.0e5, 6.0e5, 7.0e5, 6.0e5],
        "total_profit": [1.457e8, 4.82e7, 8.02e7, 6.86e7, 1.023e8],
        "income_tax": [1.75e7, 5.78e6, 9.63e6, 8.24e6, 1.23e7],
        "net_profit": [1.282e8, 4.24e7, 7.06e7, 6.04e7, 9.00e7],
        "attributable": [1.282e8, 4.24e7, 7.06e7, 6.04e7, 9.00e7],
        "non_recurring": [2.19e7, 1.59e7, 1.93e7, 2.00e7, 1.39e7],
    },
    "balance": {
        "cash": [7.4e7, 9.2e7, 8.4e7, 1.07e8, 7.1e7],
        "receivables": [6.5e7, 7.5e7, 8.5e7, 1.05e8, 9.0e7],
        "inventory": [1.10e8, 1.00e8, 1.15e8, 1.20e8, 1.10e8],
        "current_assets": [7.50e8, 7.20e8, 7.30e8, 7.60e8, 8.20e8],
        "total_assets": [1.113e9, 1.076e9, 1.109e9, 1.097e9, 1.217e9],
        "current_liabilities": [4.60e7, 3.70e7, 4.90e7, 6.10e7, 1.17e8],
        "total_liabilities": [8.68e7, 6.88e7, 8.61e7, 8.00e7, 1.349e8],
        "equity": [1.026e9, 1.007e9, 1.023e9, 1.017e9, 1.082e9],
    },
    "cashflow": {
        "sales_receipts": [4.80e8, 3.26e8, 2.98e8, 3.11e8, 2.78e8],
        "taxes_paid": [7.06e7, 3.20e7, 3.08e7, 3.66e7, 2.97e7],
        "operating": [1.85e8, 1.24e8, 7.9e7, 8.1e7, 4.3e7],
        "capex": [5.696e7, 7.87e6, 6.49e6, 1.0167e8, 1.0895e8],
    },
}


# ------------------------------------------------------------------- helpers
def _ratio(numerator: Number, denominator: Number) -> float | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return float(numerator) / float(denominator)


def _avg(prev: Number, curr: Number) -> float | None:
    if curr is None:
        return None
    if prev is None:
        return float(curr)
    return (float(prev) + float(curr)) / 2.0


def _pct(value: float | None) -> float | None:
    return None if value is None else round(value * 100.0, 2)


def _scaled(values: list[Number], factor: float) -> list[float | None]:
    return [None if v is None else round(float(v) / factor, 2) for v in values]


def _series(statements: dict[str, Any], block: str, key: str) -> list[Number]:
    data = statements.get(block)
    if not isinstance(data, dict):
        return [None] * YEARS
    values = data.get(key)
    if not isinstance(values, list):
        return [None] * YEARS
    return list(values) + [None] * (YEARS - len(values))


def _row(
    metric: str,
    unit: str,
    values: list[float | None],
    note: str | None = None,
) -> Row:
    row: Row = {"metric": metric, "unit": unit, "values": values}
    if note:
        row["note"] = note
    return row


# --------------------------------------------------------------------- engine
def compute_dashboard(statements: dict[str, Any]) -> dict[str, Any]:
    """Compute every dashboard metric from the normalized statements."""
    years = statements.get("years") or [None] * YEARS
    revenue = _series(statements, "income", "revenue")
    cost = _series(statements, "income", "cost")
    attributable = _series(statements, "income", "attributable")
    net_profit = _series(statements, "income", "net_profit")
    non_recurring = _series(statements, "income", "non_recurring")
    total_profit = _series(statements, "income", "total_profit")
    income_tax = _series(statements, "income", "income_tax")
    selling = _series(statements, "income", "selling")
    admin = _series(statements, "income", "admin")
    rd = _series(statements, "income", "rd")
    finance = _series(statements, "income", "finance")
    equity = _series(statements, "balance", "equity")
    total_assets = _series(statements, "balance", "total_assets")
    total_liabilities = _series(statements, "balance", "total_liabilities")
    current_assets = _series(statements, "balance", "current_assets")
    current_liabilities = _series(statements, "balance", "current_liabilities")
    inventory = _series(statements, "balance", "inventory")
    cash = _series(statements, "balance", "cash")
    receivables = _series(statements, "balance", "receivables")
    interest_debt = _series(statements, "balance", "interest_debt")
    receipts = _series(statements, "cashflow", "sales_receipts")
    taxes_paid = _series(statements, "cashflow", "taxes_paid")
    operating = _series(statements, "cashflow", "operating")
    capex = _series(statements, "cashflow", "capex")

    n = len(revenue)
    growth: list[float | None] = []
    for i in range(n):
        if i == 0 or revenue[i] is None or revenue[i - 1] in (None, 0):
            growth.append(None)
        else:
            growth.append(_pct(float(revenue[i]) / float(revenue[i - 1]) - 1.0))

    gross = [
        _pct(_ratio(1.0 - float(cost[i]) / float(revenue[i]), 1.0))
        if cost[i] is not None and revenue[i] not in (None, 0)
        else None
        for i in range(n)
    ]
    net_margin = [_pct(_ratio(attributable[i], revenue[i])) for i in range(n)]
    roe = [_pct(_ratio(attributable[i], equity[i])) for i in range(n)]
    deducted = [
        None
        if attributable[i] is None
        else round(float(attributable[i]) - float(non_recurring[i] or 0.0), 2)
        for i in range(n)
    ]
    selling_rate = [_pct(_ratio(selling[i], revenue[i])) for i in range(n)]
    admin_rate = [_pct(_ratio(admin[i], revenue[i])) for i in range(n)]
    rd_rate = [_pct(_ratio(rd[i], revenue[i])) for i in range(n)]
    period_rate = [
        _pct(
            _ratio(
                sum(
                    v
                    for v in (selling[i], admin[i], rd[i], finance[i])
                    if v is not None
                ),
                revenue[i],
            )
        )
        for i in range(n)
    ]
    effective_tax = [_pct(_ratio(income_tax[i], total_profit[i])) for i in range(n)]
    burden = [_pct(_ratio(taxes_paid[i], revenue[i])) for i in range(n)]
    debt_ratio = [_pct(_ratio(total_liabilities[i], total_assets[i])) for i in range(n)]
    current_ratio = [
        _ratio(current_assets[i], current_liabilities[i]) for i in range(n)
    ]
    quick_ratio = [
        _ratio(
            None
            if current_assets[i] is None or inventory[i] is None
            else float(current_assets[i]) - float(inventory[i]),
            current_liabilities[i],
        )
        for i in range(n)
    ]
    asset_turnover = [_ratio(revenue[i], total_assets[i]) for i in range(n)]
    receivable_days = [
        None
        if revenue[i] in (None, 0)
        else round(
            365.0
            * _avg(receivables[i - 1] if i > 0 else None, receivables[i])
            / float(revenue[i]),
            1,
        )
        for i in range(n)
    ]
    inventory_days = [
        None
        if cost[i] in (None, 0)
        else round(
            365.0
            * _avg(
                inventory[i - 1] if i > 0 else None,
                inventory[i],
            )
            / float(cost[i]),
            1,
        )
        for i in range(n)
    ]
    cash_ratio = [_ratio(receipts[i], revenue[i]) for i in range(n)]
    net_cash_ratio = [_ratio(operating[i], net_profit[i]) for i in range(n)]
    fcf = [
        None
        if operating[i] is None
        else round((float(operating[i]) - float(capex[i] or 0.0)) / 1e6, 2)
        for i in range(n)
    ]
    recurring_share = [
        _pct(_ratio(non_recurring[i], attributable[i])) for i in range(n)
    ]

    rows = [
        _row("营业收入", "亿元", _scaled(revenue, 1e8)),
        _row("营收同比", "%", growth),
        _row("归母净利润", "千万元", _scaled(attributable, 1e7)),
        _row("扣非归母净利润", "千万元", _scaled(deducted, 1e7)),
        _row("非经常性损益占归母净利", "%", recurring_share),
        _row("归母净利率", "%", net_margin),
        _row("毛利率", "%", gross),
        _row("ROE", "%", roe, note="归母净利润/年末归母权益"),
        _row("销售费用率", "%", selling_rate),
        _row("管理费用率", "%", admin_rate),
        _row("研发费用率", "%", rd_rate),
        _row("期间费用率合计", "%", period_rate),
        _row("实际所得税率", "%", effective_tax),
        _row("整体税负率", "%", burden, note="支付的各项税费/营业收入"),
        _row("资产负债率", "%", debt_ratio),
        _row("流动比率", "倍", [_round(v) for v in current_ratio]),
        _row("速动比率", "倍", [_round(v) for v in quick_ratio]),
        _row("货币资金", "亿元", _scaled(cash, 1e8)),
        _row("有息负债", "亿元", _scaled(interest_debt, 1e8), note="未披露则为空"),
        _row("经营净现金流", "亿元", _scaled(operating, 1e8)),
        _row("收现比", "倍", [_round(v, 3) for v in cash_ratio]),
        _row("净现比", "倍", [_round(v, 3) for v in net_cash_ratio]),
        _row("总资产周转率", "次", [_round(v, 3) for v in asset_turnover]),
        _row("应收周转天数", "天", receivable_days),
        _row("存货周转天数", "天", inventory_days),
        _row("资本性支出", "百万元", _scaled(capex, 1e6)),
        _row("简化自由现金流", "百万元", fcf, note="经营净现金流-资本开支"),
    ]
    return {
        "company": statements.get("company"),
        "unit": "元",
        "years": years,
        "rows": rows,
    }


def _round(value: float | None, digits: int = 2) -> float | None:
    return None if value is None else round(value, digits)


# ----------------------------------------------------------------------- cli
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--input", type=Path, help="statements.json 路径")
    parser.add_argument("--out", type=Path, help="看板输出路径，缺省打印到 stdout")
    parser.add_argument("--sample", action="store_true", help="用示例数据跑一遍")
    parser.add_argument(
        "--sample-statements", action="store_true", help="打印示例 statements.json"
    )
    args = parser.parse_args()

    if args.sample_statements:
        payload = json.dumps(SAMPLE_STATEMENTS, ensure_ascii=False, indent=2)
    else:
        if args.sample:
            statements = SAMPLE_STATEMENTS
        elif args.input:
            statements = json.loads(args.input.read_text(encoding="utf-8"))
        else:
            parser.error("需要 --input、--sample 或 --sample-statements 之一")
            return 2
        dashboard = compute_dashboard(statements)
        payload = json.dumps(dashboard, ensure_ascii=False, indent=2)

    if args.out:
        args.out.write_text(payload + "\n", encoding="utf-8")
        print(f"written: {args.out}", file=sys.stderr)
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
