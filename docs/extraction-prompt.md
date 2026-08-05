# Extraction prompt

**Version: 2** — bump this whenever any section body changes.

Changing a prompt invalidates every `confidence` score derived under the old one, because
confidence comes from diffing passes and passes are only comparable if they were asked the
same question. `scripts/extract.py` records this version in every extraction file.

## What changed in v2

v1 asked for everything in one call. It returned excellent eligibility rules and the
complete 24-cell 档位 table, and **zero** exclusion clauses — despite naming 不得 / 除外 /
已享受 explicitly.

The cause wasn't wording. Final recall is 5 chunks, and one call asking for eligibility,
amounts, exclusions, and procedure spends all five on whatever scores highest for the query
as a whole — which is the eligibility and amount text. The 附则 never got a look in.

v2 splits into one call per section. Each gets its own 5-chunk budget. A dedicated
exclusion query immediately surfaced candidate 不得 clauses that v1 never saw.

## What a better prompt can and cannot fix

Four error classes, and only three respond to prompting:

| Class | Example seen | Fixable by prompt? |
|---|---|---|
| **Framing** — model asked to adjudicate | 低收入家庭 assigned 第六档 (¥1,200) instead of 第二档 (¥3,000), anchored on the eligibility ceiling | **Yes.** Extraction framing removed it entirely — v1 returned the correct categorical tiers |
| **Recall** — clause exists, not retrieved | no exclusion clauses in v1 | **Yes**, by splitting queries so each section gets its own recall budget |
| **Format** — ignores output spec | asked for JSON, returned markdown | **No.** The app's console system prompt (基础文档问答) wins. Needs a second app configured for extraction |
| **Fabrication** — confident invented clause | one pass quoted a 不得申请 clause another pass says doesn't exist | **No.** No prompt makes a model reliably know what it doesn't know |

That last row is why the multi-pass cross-check exists and why a human still signs off.
Prompting improves what gets retrieved; it cannot establish that retrieved text is real.
See `data/extractions/bj_housing_market_rent_subsidy/20260806-exclusions-CONFLICT.md`.

---

## Preamble

Prepended to every section. `{program_name}` is substituted.

```text
你是政策条文抽取工具，从知识库中的政策原文提取结构化信息。

目标政策：{program_name}

严格要求：
1. 不得假设任何信息。只输出政策原文中明确写明的内容。
2. 不要判断任何人的资格，不要设想申请人。
3. 不要提供文号、网址或发文机关——这些由人工录入，你提供的会被丢弃。
4. 每一项都必须附政策原句，不要改写。
5. 知识库中没有的，明确写"未检索到"。不要推测，不要用常识补充，
   不要输出你认为"应该存在"的条款。
```

## Section: eligibility

```text
只回答申请资格条件，不要涉及补贴金额、排除条款或申请流程。

逐条列出申请人必须满足的条件，每条给出：需要知道的事实、比较方式、门槛值、政策原句。
若某个门槛随家庭人口、区域等因素变化，列出每一种取值，不要只举一例。
```

## Section: benefit

```text
只回答补贴金额，不要涉及资格条件或申请流程。

列出补贴标准的完整表格。若金额随收入档次、家庭人口、区域等因素变化，
必须列出每一档、每一类、每一区域的取值——不要只举一例，不要用"以此类推"。
另外说明：发放周期、封顶规则（如补贴不得超过实际租金）、提档或增额条件。
```

## Section: exclusions

```text
只回答排除性与终止性条款，不要重复申请条件和补贴标准。

逐条检索并列出原文中含以下表述的条款，每条附政策原句：
1. "不得"（如不得同时享受、不得重复申领）
2. "除外" / "不适用"
3. "已享受"（尤其是与公共租赁住房、公租房货币补贴、廉租房、经济适用房等
   其他保障方式的关系）
4. "停止发放" / "取消资格" / "不再发放" / "退出"
5. 骗取、隐瞒、虚报的处理条款
6. 需要主动申报变化的情形及期限

如果知识库中确实没有某一类条款，必须明确写"未检索到"。
宁可漏报，不可编造：编造一条看似合理的禁止性条款，比漏掉它危害更大。
```

## Section: procedure

```text
只回答申请流程与所需材料，不要涉及资格条件或补贴金额。

列出：申请步骤（按顺序）、受理部门、所需证明材料、审核环节、发放方式。
```
