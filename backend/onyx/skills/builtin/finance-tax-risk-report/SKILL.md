---
name: finance-tax-risk-report
description: >-
  撰写五年期上市公司财税与经营风险分析报告：老板 KPI 看板、三表五年透视、税负与现金流
  专项、TX/OP 风险识别与评分矩阵、四维改进建议、30/90 日整改清单与闭环式结论，产出带
  目录、表格与图表的正式 Word 报告。以年报 PDF 为第一证据；用同花顺取财务与行业对标，
  企查查核验工商股权司法，智慧芽补专利研发；用 chart-gen、data-viz-gen 出图。
  触发词：财税风险分析报告、经营风险识别、财税风险、风险矩阵、风险评级、五年财务分析、
  财税合规建议。
optional-mcp:
  - hithink-meta
  - hithink-a-share
  - hithink-a-share-index
  - qcc-company
  - qcc-risk
  - qcc-executive
  - qcc-operation
  - qcc-legal-case
  - company-credit
  - company-profile
  - company-risk
---

# 财税与经营风险分析报告

把一家上市公司近五个年度的财报做成一份老板能直接用的财税与经营风险诊断报告。
先建数，再识险，后成稿。不做估值，不给买卖点。

报告回答六个问题：

1. 五年里哪些指标在变好，哪些在恶化？
2. 利润是不是真的？现金能不能验证利润？
3. 税交得对不对、稳不稳？优惠能不能持续？
4. 钱花在哪了，还够不够？债扛不扛得住？
5. 哪些风险必须马上处理，哪些只需持续监控？
6. 下一步 30 天、90 天做什么？

方法细节见 `references/`。本文件只写 Onyx Craft 里怎么取数、怎么跑脚本、怎么交付。

## 何时使用

用户要写财税风险分析报告、经营风险识别报告、五年财务与税负分析、风险矩阵与整改建议，
或给出多个年度的年报 PDF 要求成稿。

单期财报解读走 `financial-report-analysis`。深度信用法律审查走 `listed-co-credit-legal`。
红蓝复核走 `listed-co-red-blue-review`。

## 数据源优先级

先用已连接的官方 MCP。未认证就说未认证，改走上传件或公开网页。不要臆造数字。

| 需要 | 先读哪个技能 | 用哪些 MCP / 工具 |
| --- | --- | --- |
| 公司名 → 代码 | `listed-co-entity-resolve` | `hithink-meta`，必要时 `qcc-company` |
| 五年财务数据 | 上传年报 PDF 为第一证据 | `hithink-a-share` 交叉核对与补缺 |
| 行业与同业对标 | `listed-co-industry-context` | `hithink-a-share-index` |
| 工商、股权、司法、处罚 | `qichacha` | `qcc-company`，`qcc-risk`，`qcc-executive`，`qcc-operation`，`qcc-legal-case` |
| 专利与研发线索 | `zhihuiya` | `company-profile`，`company-risk`；深挖再加 `patsnap-search` |
| 期后事项与舆情 | 内置 `websearch` → `webfetch` | 巨潮、交易所、公司 IR、监管问询 |

规则：

- 不要开齐全部企查查或智慧芽服务器。一次任务只用上表里需要的那几个。
- 不要跑 `qcc`、`qcc-agent-cli`、`hithink-finance-cli`。走网关 MCP。
- 原始 JSON 存 `outputs/mcp/hithink/`、`outputs/mcp/qichacha/`、`outputs/mcp/zhihuiya/`，
  仅作内部存档与复核，不进报告。
- 上传的年报 PDF 是第一证据。MCP 数字用来交叉核对与补缺，冲突时以 PDF 披露为准并写明差异。
- 研报或媒体转述必须标「转述」或「估算」。不要写成管理层原话。
- 拿不到就写「未获取」，并写原因。

报告引用来源的写法（给老板看的，不要暴露内部痕迹）：

| 数据来自 | 报告里怎么写 |
| --- | --- |
| 上传 / 下载的年报 | 「公司 2024 年年度报告第 5 页」 |
| 企查查（qcc-*） | 「企查查行政处罚记录，文号 甬市监罚〔2024〕XX 号」 |
| 智慧芽（company-* / patsnap-*） | 「智慧芽专利检索，专利 CN2024XXXXXXX.X」 |
| 同花顺（hithink-*） | 「同花顺（iFinD），同业公司 2024 年毛利率」 |
| 网页 / 公告 | 原始 URL + 访问日期，如「巨潮资讯网公告，2026-02-11」 |

禁止写进报告：MCP 工具名与服务器名（qcc-company、hithink-a-share 等）、
`outputs/` 等内部文件路径、脚本名。

## 上传文件

`attachments/` 里有年报 PDF 时直接用；没有就用 `websearch` / `webfetch` 从巨潮下载。

```
python .opencode/skills/finance-tax-risk-report/scripts/extract_annual_report.py \
  --pdf attachments/雪龙集团2024.pdf --year 2024 --out outputs/analysis
```

脚本用 pypdf 书签定位：主要会计数据（第二节）、管理层讨论与分析（第三节）、
重要事项（第六节）、财务报告（第十节）。表格页可加 `--tables` 用 pdfplumber 抽。
审计意见必须读：非标准无保留意见升级为头号风险。会计政策变更记录进可比性提示。

## 工作流程

### 0. 识别主体与报告期

写出 `outputs/entity.json`：官方名、证券代码、交易所、统一社会信用代码（能取到时）。
名字对不上就停，不要猜代码。

确定五个分析年度与期后观察窗口。写清口径：合并报表，数据时点各年 12 月 31 日。

### 1. 建五年三表

把五年的利润表、资产负债表、现金流量表整理成 `outputs/analysis/statements.json`，
格式见 `scripts/compute_metrics.py --sample`。缺的科目留空，不要补假数。单位写元。

### 2. 指标计算

```
python .opencode/skills/finance-tax-risk-report/scripts/compute_metrics.py \
  --input outputs/analysis/statements.json --out outputs/analysis/kpi_dashboard.json
```

派生指标全部用公式算，不手填。口径必须写进报告，见 `references/metrics-handbook.md`。
客户集中度、分红总额、理财结构等报表外指标单独建 `outputs/analysis/extra_kpi.json`
并标来源。

### 3. 补充数据（按需，不要全套都跑）

- 同花顺：行业增速、同业关键比率，用于对标表。
- 企查查：股权结构、涉诉、行政处罚、经营异常，用于治理与合规章节。
- 智慧芽：专利数量与质量，用于研发与技术风险。
- 公开网页：期后事项（最新季报、半年报、高管变动、定增、诉讼）、监管问询、行业数据。

### 4. 风险识别

按 `references/risk-framework.md` 扫描。财税风险编 TX-01～TX-10，经营风险编
OP-01～OP-08。每条写成三段式：数据证据 → 成因分析 → 潜在影响。
重大专题（投资失败、募投变更、审计机构更换、实控人变动等）单独成章，不进矩阵。

### 5. 图表

趋势、结构、对比用 `chart-gen`；KPI 快照看板用 `data-viz-gen`；利润桥接、同业雷达
等特殊图用 matplotlib。不要 `npm install`。标准图表清单见
`references/report-template.md`，至少产出：营收利润趋势、盈利能力、利润与现金流
对比、费用结构、风险矩阵热力图。图放 `outputs/charts/`。

### 6. 撰写报告

复制 `assets/report_template.md` 到 `outputs/`，按 `references/report-template.md`
逐章填充。章节结构、表格列式以模板为准，不要自创。章号由脚本自动连续编号，
写作时不必手工对齐。数字必须能指到年报页码、原始来源名称或网页 URL。

### 7. 生成 Word

```
python .opencode/skills/finance-tax-risk-report/scripts/build_report_docx.py \
  --input outputs/雪龙集团_财税与经营风险分析报告.md \
  --output outputs/雪龙集团_财税与经营风险分析报告.docx
```

脚本自动生成真目录域、连续章号、提示框底纹与表格样式。生成后逐条过
`references/quality-checklist.md`，再交付。聊天里给摘要、路径和引用，
不要把整份文档贴进对话。

## 硬规则

1. 每个数字可溯源：年报页码、原始来源名称（企查查 / 智慧芽 / 同花顺，注明具体
   数据项），或网页 URL。三选一。报告正文不得出现 MCP 工具名、服务器名或内部
   文件路径。
2. 跨年比较先检查会计政策变更。口径变了要写明，不能机械横比。
3. 期后事项（未审计数据）单独成章，标注「未经审计，仅作趋势观察」。
4. 风险等级只有高 / 中 / 低，评分映射 56 / 20 / 4。不要发明新等级。
5. 结论必须给「闭环」：收入→扣非利润→现金流→资产回报→内控覆盖，逐条回答。
6. 免责声明必须保留。这是分析框架，不是投资建议。

## 免责声明

报告依赖公开披露与检索，可能有时效和口径偏差。这是分析框架，不是投资建议，
不构成税务申报意见或审计意见。重大决策前应与年度审计报告、监管问询函回复交叉验证。
