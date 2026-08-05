# Exclusion clauses: UNRESOLVED

Two passes of the identical query against the same app disagree on every item.

| Item | Pass 1 | Pass 2 |
|---|---|---|
| 已享受保障房 → 不得申请 | quoted clause | 未检索到 |
| 停止发放 conditions | 2 quoted clauses | not found |
| 骗取 → 取消资格/追回 | quoted clause | not found, only 「防范骗租骗补行为发生」 |
| 30日申报期限 | quoted clause | not found |

Both cite the SAME URL (…/543338945/index.shtml) under DIFFERENT titles:
  pass 1: 关于进一步规范市场租房补贴发放管理有关工作的通知
  pass 2: 关于调整本市市场租房补贴申请条件及补贴标准的通知
At least one attribution is wrong.

## Why nothing here is encoded

Pass 1's clauses are specific, well-formed, and exactly what this policy would be
expected to say — which makes them a textbook confabulation risk, not a reassurance.
Pass 2 does not merely omit them; it states positively that the corpus lacks any
prohibitive language and offers the non-prohibitive text it did find instead.

A single pass would have produced a confident, quoted, apparently-sourced rule.
The disagreement is the finding.

## What resolves it

A human opens the PDF and searches for 不得 / 已享受 / 停止发放. Nothing else does.
Until then `data/programs/bj_housing_market_rent_subsidy.json` carries no exclusion
predicate, and `exclusivity_group: "bj_housing"` remains a hand-asserted link with
no source clause behind it.
