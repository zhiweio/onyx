---
name: financial-report-analysis
description: >-
  解读最新季报或年报：融合三表同比环比与 10 项异常检测，再建近 8 季单季趋势、经营 KPI
  与业绩指引。支持用户上传 PDF / Excel / 图片，或用同花顺、企查查、智慧芽查询财务、
  工商与舆情。出图按交付分流：Word 用 vivid-figures-skill（chart-gen 备选）出 PNG，
  HTML 由 slideblocks 内置渲染路径绘制。交付双报告：
  slideblocks 生成的报告型 HTML 与 docx 技能渲染的专业 Word。
  触发词：财报解读、三表、同比、
  环比、异常检测、业绩说明会、单车均价、市占率、读生意。
optional-mcp:
  - hithink-meta
  - hithink-a-share
  - hithink-a-share-index
  - qcc-company
  - qcc-risk
  - qcc-legal-case
  - qcc-executive
  - qcc-operation
  - company-credit
  - company-profile
  - company-risk
---

# 财报解读

把一家公司的最新财报做成可核验的解读。先建数据，再扫异常，再读生意与指引。
不做估值，不做买卖点。

报告要回答六个问题：

1. 近几个季度在变好还是变坏？
2. 有没有勾稽或序列上的红旗？
3. 账面健不健康？
4. 是不是一门好生意，钱分得对不对？
5. 管理层下一步怎么说？
6. 用量、价、结构、份额、单位经济解释财务结果。

方法细节见 `references/`。本文件只写 Onyx Craft 里怎么取数、怎么跑脚本、怎么交付。

## 何时使用

用户要解读财报、分析最新季报或年报、看三表同比环比、扫财务异常、读生意、
看业绩说明会，或问单车均价、市占率、客单价、NDR。

用户上传了财报 PDF、Excel 或图片，也走本技能。

不要用本技能做行情报价或估值。深度信用法律审查走 `listed-co-credit-legal`。
完整上市审计包走 `listed-company-financial-audit` 场景。

## 数据源优先级

先用已连接的官方 MCP。未认证就说未认证，改走上传件或公开网页。不要臆造数字。

| 需要 | 先读哪个技能 | 用哪些 MCP / 工具 |
| --- | --- | --- |
| 公司名 → 代码 | `listed-co-entity-resolve` | `hithink-meta`，必要时 `qcc-company` |
| 上市财务与公告 | `hithink-finance`，`listed-co-filings-normalize` | `hithink-a-share`，同业用 `hithink-a-share-index` |
| 用户上传 PDF / Excel / 图片 | `document-ingest`，`pdf`，`xlsx` | 无 MCP |
| 工商、股权、诉讼 | `qichacha` | `qcc-company`，`qcc-risk`，`qcc-legal-case`，`qcc-executive` |
| 主体信用与专利线索 | `zhihuiya` | `company-credit`，`company-profile`，`company-risk` |
| 内部纪要、旧报告 | `company-search` | `onyx-cli search` |
| 官方披露、纪要、舆情 | 内置 `websearch` → `webfetch` | 巨潮、交易所、公司 IR、上证 e 互动 |

规则：

- 不要开齐全部企查查或智慧芽服务器。一次任务只用上表里需要的那几个。
- 不要跑 `qcc`、`qcc-agent-cli`、`hithink-finance-cli`。走网关 MCP。
- 原始 JSON 存 `outputs/mcp/hithink/`、`outputs/mcp/qichacha/`、`outputs/mcp/zhihuiya/`，
  仅作内部存档与复核，不进报告。
- 网页先 `websearch`，再 `webfetch` 打开具体 URL。优先巨潮、上交所、深交所、港交所、公司 IR。
- 研报或媒体转述必须标「转述」或「估算」。不要写成管理层原话。
- 拿不到就写「未获取」，并写原因。

报告引用来源的写法（面向读者，不暴露内部痕迹）：

| 数据来自 | 报告里怎么写 |
| --- | --- |
| 上传 / 下载的财报 | 「公司 2025 年年度报告第 47 页」 |
| 企查查（qcc-*） | 「企查查行政处罚记录，文号 甬市监罚〔2024〕XX 号」 |
| 智慧芽（company-* / patsnap-*） | 「智慧芽专利检索，专利 CN2024XXXXXXX.X」 |
| 同花顺（hithink-*） | 「同花顺（iFinD），同业公司 2025Q3 毛利率」 |
| 网页 / 公告 | 原始 URL + 访问日期，如「巨潮资讯网公告，2026-02-11」 |

禁止写进报告：MCP 工具名与服务器名（qcc-company、hithink-a-share 等）、
`outputs/`、`/tmp/` 等内部或临时文件路径、脚本名。报告头部「来源」只写
数据源名称（如「公司定期报告 / 同花顺（iFinD）/ 公开检索」）。

## 上传文件

`attachments/` 里有财报时：

```
python .opencode/skills/document-ingest/scripts/ingest.py \
  --roots attachments --out outputs
```

数字 PDF 用 `pdfplumber` 抽表。Excel 用 `xlsx` / `openpyxl`，有公式先重算。
扫描件或图片按 `document-ingest` 的 `needs_vision` 分批读，不要一次塞完全部页。

把抽出的三表整理成 `outputs/analysis/statements.json`，格式见
`scripts/analyze_financials.py --sample`。缺的科目留空，不要补假数。

A 股或港股定期报告是累计口径。整理完后必须拆单季，见下一步。

## 工作流程

### 0. 识别主体与报告期

写出 `outputs/entity.json`：官方名、证券代码、交易所、统一社会信用代码（能取到时）。
名字对不上就停，不要猜代码。

确定最新已披露期。写清财年口径（例如微软 6 月年结）。

### 1. 建三表序列

目标是近 8 季。要拆累计首季，至少再多取 4 期。

已连接同花顺：按 `hithink-finance` 取财务与公告，保存原始体。
有上传件：以上传件为第一证据，MCP 数字用来交叉核对。
两边都没有：用 `websearch` / `webfetch` 打开巨潮或公司 IR 的 PDF。

写成 `outputs/analysis/statements.json`（Kimi 三表格式）。`unit` 必须写清
（元 / 万元 / 亿元）。`normalize_statements.py` 写趋势输入时会把金额换成元。

### 2. 量化：同比环比 + 10 项异常

```
python .opencode/skills/financial-report-analysis/scripts/normalize_statements.py \
  --input outputs/analysis/statements.json \
  --statements outputs/analysis/statements.json \
  --trend outputs/analysis/trend_input.json

python .opencode/skills/financial-report-analysis/scripts/analyze_financials.py \
  outputs/analysis/statements.json --json \
  --output outputs/analysis/anomalies.json
```

这 10 项规则来自 Kimi `financial-report-reader`：应收暴增、现金流背离利润、
存货积压、毛利率突变、净利率突变、OCF 连续为负、商誉过高、资产负债率过高、
流动比率过低、应付异常。

### 3. 累计拆单季 + 趋势五看

A 股 / 港股累计口径必须拆单季。不要拿半年报当二季度。

```
python .opencode/skills/financial-report-analysis/scripts/quarterly_trend.py \
  --input outputs/analysis/trend_input.json --market A --quarters 8 --out html \
  > outputs/analysis/quarterly_trend.html
```

港股用 `--market HK`。美股或非 12 月年结加 `--market US --fy-end 6`。

趋势方法见 `references/quarterly_trend_analysis.md`。水平与趋势冲突时，以趋势为准。

### 4. 经营 KPI

财务数字是结果。经营指标是原因。每次解读都要有 3～6 个核心 KPI。
行业清单见 `references/industry_kpi_library.md`。

数据来自公司月报、分部附注、行业协会、业绩会。写入
`outputs/analysis/kpi.json` 后：

```
python .opencode/skills/financial-report-analysis/scripts/operating_kpi.py \
  --input outputs/analysis/kpi.json --out html \
  > outputs/analysis/kpi.html
```

派生指标用公式算，不手填。口径必须写在报告里。

### 5. 支撑证据：工商、信用、公开舆情

按主体需要取，不要每家公司全套都跑。

- 企查查：登记状态、股权、失信、诉讼。工具见 `qichacha`。
- 智慧芽：`company-credit` / `company-profile` / `company-risk`。专利深挖才加
  `patsnap-search`。
- 内部知识：`company-search` / `onyx-cli search`。
- 公开网页：业绩说明会纪要、监管问询、行业销量、舆情。先搜后抓。

指引分四类：增长战略、产业判断、资本开支、分业务展望。
对照当期数据与季度序列，写清是否兑现。

### 6. 图表

至少产出 8 张，覆盖每个数据章节。两份报告的图表清单一致，但各自出图：

1. 单季营收与归母净利趋势
2. 营收 / 净利单季 YoY 增速
3. 毛利率与净利率逐季
4. 费用率结构（销售 / 管理 / 研发 / 财务）
5. 净利润 vs 经营现金流对比
6. 资产负债结构与偿债（负债率、有息负债）
7. 经营 KPI（量 / 价 / 结构 / 份额，至少一张）
8. 异常项预警卡或健康度快照

数据够时增补：扣非缺口、TTM ROE、同业对比。每张图有图注与来源行。

**Word 报告的图**：优先用 `vivid-figures-skill`：按数据与目的在 `catalog/` 选配方，
保真复用配方源码出图（折线、柱状、面积、热力图等均有完整配方）。
快速简单图退回 `chart-gen`：

```
node .opencode/skills/chart-gen/scripts/chart.mjs \
  --type line \
  --data '[{"x":"2024Q1","y":100},{"x":"2024Q2","y":112}]' \
  --title "单季营收" --x-title 报告期 --y-title 亿元 \
  --output outputs/charts/revenue_q.png
```

KPI 快照或对比看板用 matplotlib 出静态 PNG（多子图拼一页）。
Word 用图一律 PNG，放 `outputs/charts/`。Sandbox 已预装 Vega 与 infographic
脚本。不要再 `npm install`。

**HTML 报告的图**：一律用 `slideblocks` 的内置渲染路径（`diagram:mermaid`、
`figure:comparison`、`figure:annotated`、`figure:graph`、`diagram:elk`、
`direct-svg`）在 HTML 内直接绘制，数据取自 `outputs/analysis/`。不得把其他技能
或外部工具产出的 PNG/SVG 嵌入 HTML 报告。

### 7. 健康度与综合结论

每个财务维度给「健康 / 关注 / 预警」。阈值见
`references/financial_health_criteria.md`。
异常项作为首要关注。经营指标与财务结论冲突时，以经营指标为先行变量并解释差异。

银行、保险、券商不要套收现比和 FCF。改看不良率、拨备、资本充足率、净息差。

### 8. 交付双报告（HTML + Word）

报告章节与内容要求见 `references/output_template.md`，读者版引用与编辑规范见上文。

**HTML 报告（slideblocks）**：用 `slideblocks` 技能生成报告型 HTML，
按报告版式组织：封面（公司、代码、报告期、数据时点）、执行摘要与健康度总评、
分项诊断（图表 + 表格）、生意与指引、综合结论、免责声明。图表按上文「HTML 报告的图」
用 `slideblocks` 内置渲染路径绘制，每页数据带来源行。交付自包含
`offline.html`，复制为 `outputs/{公司名}_财报解读_{YYYY}Q{n}.html`。

**Word 报告（docx 技能）**：按 `references/docx-report-template.md` 的契约组织：
封面、目录、执行摘要、正文（沿用 output_template 的章节脊柱）、
图表编号 + 图注 + 来源行、数据来源与方法、免责声明。用 `docx` 技能
（python-docx）渲染 `outputs/{公司名}_财报解读_{YYYY}Q{n}.docx`。

两份报告数据与结论必须一致，出自同一套 `outputs/analysis/` 数据；图表按 §6 分流，
清单一致。

**自检后交付**：

```
python .opencode/skills/financial-report-analysis/scripts/self_check_report.py \
  "outputs/{公司名}_财报解读_{YYYY}Q{n}.html" --min-figures 8
python .opencode/skills/financial-report-analysis/scripts/self_check_report.py \
  "outputs/{公司名}_财报解读_{YYYY}Q{n}.docx" --min-figures 8
```

FAIL 项修完再交付。聊天里给摘要、路径和引用。不要把整份报告贴进对话。

## 硬规则

1. 带 `_Q` 的增速才是单季。不要把累计增速当单季读。
2. 周转率与累计 ROE 只能同比同期比，或改用 TTM。
3. 强季节性行业以 YoY 为主。
4. 每个数字可溯源，三选一：来源文件页码（如「2025 年年报第 47 页」）、
   原始来源名称（企查查 / 智慧芽 / 同花顺，注明具体数据项）、网页 URL + 访问日期。
5. 报告正文（HTML 页面与 Word 文档）不得出现 MCP 工具名、服务器名、
   `outputs/`、`/tmp/` 等内部或临时文件路径、脚本名，也不得出现
   「草稿 / 待修改 / 待补充 / TODO」等未定稿标记。
6. 禁止把年度值插值成季度值。
7. 编辑规范：结论先行；口径与量纲随数字注明；不留 `{{占位符}}`；
   图表编号连续，每图有图注与来源行；数据缺口写「未获取」并写原因。

## 免责声明

报告依赖公开披露与检索，可能有时效和口径偏差。这是分析框架，不是投资建议。
