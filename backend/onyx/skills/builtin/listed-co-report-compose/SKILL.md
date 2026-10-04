---
name: listed-co-report-compose
description: Compose the listed-company financial-audit report under the listed_company_audit contract. Use for 审计报告, 财税风险报告, or report compose.
---

# listed-co-report-compose

Compose `outputs/report.md` under the `listed_company_audit` template
contract: follow the spine acts, include every required element, and keep
chapter numbers continuous. The platform renders the formal Word version at
export — do not hand-write a docx converter, and do not keep a parallel
markdown summary.

## 引用与痕迹（硬规则）

- 每个数字按读者版写法溯源：年报页码（如「2024 年年度报告第 81 页」）、
  原始来源名称 + 数据项（企查查 / 智慧芽 / 同花顺（iFinD）），或网页 URL + 访问日期。
- 正文不出现 MCP 工具名、服务器名（qcc-*、hithink-* 等）、`outputs/`、
  `/tmp/` 等内部或临时路径、脚本名。来源行（来源：…）放在每张表和每张图下。
- 图表不少于契约下限，一律 `outputs/charts/` 下的 PNG，图注「图表N + 标题 +
  来源行」，编号连续。
- 无 `{{占位符}}`，无草稿 / 待修改 / TODO 标记；免责声明保留在文末。

## 交付前自检

用平台工具 `check_report`（传 `markdown` 与 `listed_company_audit` 契约）
逐条自检：占位符、必备产物、章号、图表数、来源行、内部与临时路径、
MCP 名、草稿标记。FAIL 项修完再交付。
红蓝复核未关闭的质疑写进「未关闭质疑」小节，不得写成结论。
