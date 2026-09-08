---
name: tax-closing-checklist
description: Drive a Chinese month-end or period-end close as a tracked checklist by module (银行, 往来, 存货, 收入, 成本, 费用, 税金, 固定资产, 薪酬, 结转, 报表), with evidence and a blocking-exception rule per item, in the right close sequence. Use for 关账, 月结, 结账, 期末结账, period close, month-end close, or close checklist.
---

# tax-closing-checklist

Run a period close as a tracked checklist, not prose.
Delegate the heavy reconciliations to the sibling skills and pull their results
back into the checklist. An unexplained difference blocks the close — record it as
blocking; do not close around it.

## Inputs contract

Required:
- The entity, period start/end, 币种, and the close deadline.
- The scope: which modules are in play this period.

Per module, the underlying data (whatever exists):
- 银行对账单 + 日记账; AR/AP 明细 + 对账/函证; 存货盘点表; 收入/开票明细;
  费用/计提底稿; 税金申报表; 固定资产/无形资产台账; 薪酬/社保表; 上期科目余额表.

If a module's inputs are missing, mark its items `blocked` with the reason; do not
silently skip a module or mark it done without evidence.

## Phases

1. **plan** — Write `outputs/PLAN.md`: entity, period, 币种, deadline, and the
   modules in scope. Done when scope and deadline are fixed.
2. **ingest** — Run `document-ingest` on the module inputs. Done when every input
   has a MANIFEST row.
3. **build** — Write `outputs/normalized/close_checklist.csv`, one row per task,
   with module, sequence, owner, and a required evidence type. Done when every
   in-scope module has its tasks.
4. **execute** — Work the modules in sequence, delegating recon to sibling skills
   and recording evidence paths and exceptions. Done when every task is `done` or
   `blocked`.
5. **resolve** — Clear or escalate every exception in
   `outputs/exceptions/close_exceptions.csv`. Done when no blocking exception is
   open, or each open one is explicitly escalated.
6. **report** — Write the checklist state, open exceptions with amounts, and the
   sign-off readiness to `outputs/markdown/`. Done when the report ties to the
   checklist and exceptions files.

## Close sequence (do not reorder)

Close depends on order. Reconcile before you accrue; accrue before you carry
forward; carry forward before you produce statements:

1. **Reconcile** — 银行 and 往来 first, so balances are trustworthy.
2. **计提 / 调整** — 费用计提, 待摊摊销, 折旧/摊销, 薪酬与社保, 税金计提.
3. **结转** — 成本结转, 收入成本配比, 结转本年利润.
4. **出表** — statements and 三表勾稽.

## Module checklist (task · evidence · blocking rule)

- **银行 / 货币资金** — 银行余额调节表 per account (delegate to `tax-bank-ledger`).
  Evidence: the 调节表. **Blocks if any account is not 调平.**
- **往来 (AR/AP/其他应收应付/预收预付)** — ageing and 对账/函证 (delegate to
  `tax-recon-supplier` for payables). Evidence: 对账单/函证. **Blocks on an
  unexplained 往来 difference.**
- **存货** — 盘点表 vs 账, 计价, 跌价准备. Evidence: 盘点表. **Blocks on 负库存 or
  unexplained 账实不符.**
- **收入** — cut-off (截止) at period end; 确认 policy; reconcile 收入 to 增值税
  销项/开票. Evidence: 开票明细 + cut-off test. **Blocks on a cut-off break or a
  收入-vs-销项 gap that is unexplained.**
- **成本** — 结转 complete and matched to 收入/存货 movement. Evidence: 结转凭证.
- **费用** — accruals (计提), prepayments (待摊), amortization (摊销) posted.
  Evidence: 计提底稿. **Blocks if a known recurring accrual is missing.**
- **税金** — 增值税 (进项/销项/应交, and 申报表 vs 账), 企业所得税 预缴, 附加税,
  印花税, 个税. Evidence: 申报表 + 计提凭证. **Blocks if a 申报 amount does not tie
  to the 账.**
- **固定资产 / 无形资产 / 长期待摊** — 增减, 折旧/摊销 run for the period.
  Evidence: 台账 + 折旧表.
- **薪酬** — 工资, 社保, 公积金 计提 and 发放 reconciled. Evidence: 薪酬表.
- **结转损益** — 本年利润 结转 after all 计提/结转. Evidence: 结转凭证. **Blocks if
  any 未过账 (unposted) voucher remains in the period.**
- **报表** — statements produced and tied (delegate 三表勾稽 to
  `tax-financial-statement`). Evidence: the tie file. **Blocks on a 勾稽 break.**

## Output contract

`outputs/normalized/close_checklist.csv`:
`module, seq, task, owner, status(pending/in_progress/done/blocked), evidence_ref,
exception_ref, due, note`

`outputs/exceptions/close_exceptions.csv`:
`module, task, exception, amount, blocking(Y/N), required_action, source_ref`

The `outputs/markdown/` report shows: the checklist by module with status; the
open exceptions with amounts, blocking first; what each open exception needs to
clear; and an explicit sign-off readiness line (ready / not ready and why).

## Rules

- If `SCENARIO.md` names a Word template, fill that file. Do not invent a parallel markdown report.
- Mark an item `done` only when its evidence file exists.
- Every reconciliation states both sides and the difference. Never net an
  unexplained difference to zero.
- A blocking exception stops sign-off. Record it as blocking; do not close around
  it.
- Keep tax positions separate from book entries; note 税会差异 rather than merging
  them.
- If a step could not run, mark it `blocked` with the reason. Do not skip it
  silently.
