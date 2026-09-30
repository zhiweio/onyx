---
name: caishui-skill
description: >-
  中国大陆财税申报与财务报表工作流：纳税人画像、账单/发票/银行/支付宝/微信/工资
  资料归档与勾稽、账簿试算平衡、资产负债表与利润表底稿、增值税/附加税费/
  企业所得税/个体经营所得申报底稿、申报前检查清单与阻断项。政策核验遵循
  tax-policy-verify 的官方来源与证据卡约定。触发词：报税、申报底稿、做账、
  勾稽、增值税申报、汇算清缴底稿、财务报表编制。
optional-mcp:
  - qcc-company
  - qcc-risk
  - qcc-legal-case
  - hithink-meta
  - hithink-a-share
  - hithink-a-share-index
---

# 财税申报与报表

## 核心规程

把中国大陆财税、申报、财务报表任务视为高风险任务。区分三类输出：

1. 工作底稿：表格、计算过程、勾稽关系和假设。
2. 申报包：电子税务局填报值、导入文件、申报前检查清单。
3. 官方动作：正式提交、缴款、退税、作废、红冲、用途确认。
   没有用户明确授权和可追溯记录时，不执行也不引导不可逆动作。

凡涉及税率、优惠、申报期限、数电票、电子税务局路径或地方口径，先按
`tax-policy-verify` 技能核验官方来源并出证据卡；核验不了就写
"无法核验/待核验"，不编造政策、文号、链接或税务机关答复。

计算、申报或给确定性判断前，先取得纳税人画像（见
[taxpayer-data.md](references/taxpayer-data.md)）：主体类型、纳税人身份、
省市区与主管税务机关、行业、所属期、税种、增值税类型、征收方式、
会计准则、发票模式。缺地区时只给全国口径，并标明"地方口径未核验"。

## MCP 与实时数据

- 企查查 MCP 可用时：核验主体工商登记、行政处罚、司法涉诉；把记录号
  写进底稿来源。
- 同花顺 MCP 可用时：取上市公司财务与行业对标数据，用于申报与账务的
  外部佐证。
- 政策与新闻类实时信息（新政发布、申报期调整、地方口径）用网页检索，
  并按 tax-policy-verify 的证据卡落到官方来源。
- MCP 不可用时不用替代猜测：写明缺口与下一步核验方式。

## 工作流

先判断任务类型：

- **资料归档**：读 [bill-storage-and-organization.md](references/bill-storage-and-organization.md)。
  建索引或归档副本用 `scripts/index_bills.py`。
- **财务报表**：读 [taxpayer-data.md](references/taxpayer-data.md) 与
  [statement-and-filing-workflow.md](references/statement-and-filing-workflow.md)。
  有账簿 CSV 时用 `scripts/build_financial_statements.py` 生成底稿。
- **申报准备**：读 [statement-and-filing-workflow.md](references/statement-and-filing-workflow.md)
  与 [controls-and-boundaries.md](references/controls-and-boundaries.md)。
  生成申报草稿与提交前检查清单，不做无人值守申报。
- **复核/风控**：读 [controls-and-boundaries.md](references/controls-and-boundaries.md)。
  用 `scripts/validate_workpapers.py` 检查画像、报表平衡与增值税勾稽。

`assets/templates/` 是画像、账单索引、账簿、发票台账、增值税勾稽和
申报复核清单的起点，支持中文表头。真实账单与凭证放项目归档目录，
不放进 skill 目录。

## 数据和安全

不索要、保存或转述密码、CA/UKey PIN、短信验证码、人脸认证信息、
银行扣款凭据、私钥。电子税务局实操默认只做导航辅助、截图核对、
草稿与导入文件准备；未经明确授权不提交、不缴款。

## 输出格式

实质性输出按顺序组织：

1. 范围：纳税人、地区、所属期、税种、是否已核验地方口径。
2. 结果：简明答案或生成文件/表格摘要。
3. 依据：政策证据卡（按 tax-policy-verify 格式）与关键假设。
4. 检查：勾稽差异、缺失数据、地方不确定性、阻断申报的风险。
5. 下一步：正式申报前还缺的数据、核验或用户确认。
