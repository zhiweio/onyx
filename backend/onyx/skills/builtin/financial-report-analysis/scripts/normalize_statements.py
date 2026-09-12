#!/usr/bin/env python3
"""Normalize three-statement JSON for the two analysis scripts.

Reads the Kimi ``financial-report-reader`` schema (periods + three statement
objects) and writes:

- ``--statements``: the same schema, validated, for ``analyze_financials.py``
- ``--trend``: ``{income, balance, cashflow}`` row lists for ``quarterly_trend.py``
"""

from __future__ import annotations

import argparse
import calendar
import json
import re
import sys
from typing import Any

PERIOD_Q = re.compile(r"^(\d{4})Q([1-4])$", re.IGNORECASE)
PERIOD_Y = re.compile(r"^(\d{4})$")

UNIT_TO_YUAN = {
    "元": 1.0,
    "人民币元": 1.0,
    "cny": 1.0,
    "yuan": 1.0,
    "千元": 1_000.0,
    "万元": 10_000.0,
    "亿元": 100_000_000.0,
}


def unit_scale(unit: object) -> float:
    if unit is None:
        return 1.0
    key = str(unit).strip().lower()
    if key in UNIT_TO_YUAN:
        return UNIT_TO_YUAN[key]
    compact = str(unit).strip()
    return UNIT_TO_YUAN.get(compact, 1.0)


INCOME_FIELDS = {
    "revenue": "OperatingRevenue",
    "cost_of_revenue": "OperatingCost",
    "operating_income": "OperatingProfit",
    "net_income": "NPParentCompanyOwners",
}
BALANCE_FIELDS = {
    "accounts_receivable": "AccountsReceivable",
    "inventory": "Inventories",
    "total_current_assets": "TotalCurrentAssets",
    "goodwill": "Goodwill",
    "total_assets": "TotalAssets",
    "accounts_payable": "AccountsPayable",
    "total_current_liabilities": "TotalCurrentLiabilities",
    "total_liabilities": "TotalLiabilities",
    "total_equity": "SEWithoutMI",
}
CASH_FIELDS = {
    "operating_cash_flow": "NetOperateCashFlow",
    "investing_cash_flow": "NetInvestingCashFlow",
    "financing_cash_flow": "NetFinancingCashFlow",
    "capex": "Capex",
}


def _month_end(year: int, month: int) -> str:
    last = calendar.monthrange(year, month)[1]
    return f"{year:04d}-{month:02d}-{last:02d}"


def period_end_date(period: str, fy_end_month: int) -> str:
    text = str(period).strip()
    match = PERIOD_Q.match(text)
    if match:
        year = int(match.group(1))
        quarter = int(match.group(2))
        return _month_end(year, quarter * 3)
    match = PERIOD_Y.match(text)
    if match:
        return _month_end(int(match.group(1)), fy_end_month)
    raise ValueError(f"unsupported period label: {period!r}")


def _as_list(value: Any) -> list[Any] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        raise ValueError("statement series must be lists")
    return value


def validate_statements(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    periods = data.get("periods")
    if not isinstance(periods, list) or not periods:
        return ["missing periods"]
    count = len(periods)
    for section in ("income_statement", "balance_sheet", "cash_flow"):
        block = data.get(section, {})
        if not block:
            continue
        if not isinstance(block, dict):
            errors.append(f"{section} must be an object")
            continue
        for key, values in block.items():
            if isinstance(values, list) and len(values) != count:
                errors.append(
                    f"{section}.{key} length {len(values)} != {count} periods"
                )
    return errors


def to_trend_tables(
    data: dict[str, Any], fy_end_month: int
) -> dict[str, list[dict[str, Any]]]:
    periods = [str(item) for item in data["periods"]]
    dates = [period_end_date(period, fy_end_month) for period in periods]
    income = data.get("income_statement") or {}
    balance = data.get("balance_sheet") or {}
    cash = data.get("cash_flow") or {}
    scale = unit_scale(data.get("unit"))

    def scaled(value: object) -> object:
        if value is None:
            return None
        if isinstance(value, (int, float)) and scale != 1.0:
            return float(value) * scale
        return value

    def rows(mapping: dict[str, str], source: dict[str, Any]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for index, end_date in enumerate(dates):
            row: dict[str, Any] = {"EndDate": end_date, "Period": periods[index]}
            for src_key, dest_key in mapping.items():
                series = _as_list(source.get(src_key))
                if series is None or index >= len(series):
                    continue
                row[dest_key] = scaled(series[index])
            out.append(row)
        return out

    return {
        "income": rows(INCOME_FIELDS, income),
        "balance": rows(BALANCE_FIELDS, balance),
        "cashflow": rows(CASH_FIELDS, cash),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate three-statement JSON and emit quarterly_trend input"
    )
    parser.add_argument("--input", required=True, help="Kimi-style statements JSON")
    parser.add_argument("--statements", help="Write validated statements JSON here")
    parser.add_argument("--trend", help="Write quarterly_trend input JSON here")
    parser.add_argument(
        "--fy-end",
        type=int,
        default=12,
        help="Fiscal-year end month for annual period labels (default 12)",
    )
    args = parser.parse_args()

    try:
        with open(args.input, encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        print(f"error: {args.input} not found", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as exc:
        print(f"error: invalid JSON: {exc}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(data, dict):
        print("error: root must be an object", file=sys.stderr)
        sys.exit(1)

    errors = validate_statements(data)
    if errors:
        print("validation failed:", file=sys.stderr)
        for item in errors:
            print(f"  - {item}", file=sys.stderr)
        sys.exit(1)

    try:
        trend = to_trend_tables(data, args.fy_end)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)

    if args.statements:
        with open(args.statements, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
    if args.trend:
        with open(args.trend, "w", encoding="utf-8") as handle:
            json.dump(trend, handle, ensure_ascii=False, indent=2)
            handle.write("\n")

    summary = {
        "company": data.get("company"),
        "periods": data.get("periods"),
        "unit": data.get("unit"),
        "yuan_scale": unit_scale(data.get("unit")),
        "income_rows": len(trend["income"]),
        "balance_rows": len(trend["balance"]),
        "cashflow_rows": len(trend["cashflow"]),
    }
    json.dump(summary, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
