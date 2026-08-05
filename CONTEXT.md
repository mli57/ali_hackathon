# System Design

This document explains how the subsidy matcher works, why we built it this way, and what guarantees it makes.

**Current status:** Housing programs only. Once housing is proven end-to-end, we'll add childcare and employment. See `ITERATE.md` for the roadmap.

---

## The big picture

**What it does:** Someone in Beijing answers a few questions about their household. We tell them which government cash benefits they qualify for, how much money each one is worth, and how to claim it.

**What it does NOT do:**
- We don't search the internet for policies. A human had to find and upload the official documents first.
- We don't process applications or handle credentials.
- We don't have user accounts or remember past conversations.

We're matching one household against a few known, hand-picked programs across three areas: housing, childcare, and employment.

---

## The core principle: Numbers are calculated, explanations are written

> **All money amounts and eligibility decisions are computed by code.**
> 
> **All human-readable explanations are written by AI.**

Here's why this matters: a money amount or an eligibility decision should be the same every single time—no guessing, no randomness. An AI might phrase an explanation differently each time, but the decision itself doesn't change. So we split the work:

1. **Code** handles the calculations. Given a household profile, the system looks it up in a table and returns a number. This is fast, reproducible, and auditable.
2. **AI** writes the explanation. After we know the answer, we ask the AI to phrase it in plain language. But it can't change the answer—just explain it.

This is why the system has three separate pieces (extract → match → explain), not one big AI loop.

---

## How it works: Three stages

### Stage 1: Turn policies into rules (before launch)

Before the system ever talks to anyone, we read the official government PDFs and turn them into rule objects. This happens offline, and only a human can approve the result.

```text
1. Find policy PDFs
   (downloaded from official government websites)
   
2. Upload to Bailian knowledge base
   
3. Record metadata in data/manifest.json
   (document number, official link, agency, program ID)
   
4. Run extraction script (N times for consistency)
   → AI reads the PDF and drafts rules
   
5. Compare the N drafts
   → If they all say the same thing, high confidence
   → If they disagree, flag it for review
   
6. Human review
   → Person reads PDF and the AI draft side-by-side
   → Checks every number and every condition
   → Approves or corrects
   
7. Save approved rule to data/programs/[program_id].json
   
8. Merge all program rules into data/rules.json
```

**Key design decisions:**

**Ask the AI for questions, not answers.** We don't ask "is a family eligible?" Instead we ask "list every fact you'd need to know to decide, with thresholds." Why? When we ask AI to judge eligibility of a made-up family, it often invents household details to justify a yes. When we ask for the rules themselves (no family in context), there's nothing to invent.

**Hunt for exclusions explicitly.** We tell the AI: "also look for clauses that say who is NOT eligible (不得 / 除外 / 已享受)." It's easy to miss disqualifying clauses if you're only looking for positive conditions. A missed "you can't have this if..." sends real people to the wrong government office.

**Never let AI invent sources.** The document number (文号), official link, and agency name come from `data/manifest.json`, which a human fills in when uploading. Why? A fake 文号 on a results card looks like proof but isn't. The person who downloaded the PDF knows the real number. The AI doesn't.

**Declare conflicts manually.** Two programs might exclude each other (you can only get one). This usually lives as one sentence scattered across two documents. We don't trust extraction to find it for both programs, so we manually set `exclusivity_group` in the data. The build script then verifies both programs declare it.

### Stage 2: Match a household to programs (when someone uses it)

No AI involved. Pure code. Fast, reliable, always the same answer.

```text
1. User fills in household info
   (income, family size, property, etc.)
   
2. Code normalizes the data
   → Calculate per-capita income
   → Assign income tier (第1档, 第2档, etc.)
   → Assign household-size bucket (1-3 people, 4+, etc.)
   → Assign district group
   
3. For each program rule:
   → Check if all conditions match (income ≤ threshold? owns property? etc.)
   
4. For matched programs:
   → Look up payment amount in the table
   → Apply any caps (e.g., "not more than actual rent paid")
   
5. Handle conflicts
   → Some programs exclude each other (pick the higher payment)
   → Separate monthly payments from one-time grants
   → Sort by confidence and amount
   
6. Return the final list
   → Which programs they qualify for
   → How much for each
   → Any conditions that still need verification
```

**Why one file (derive.py) for normalization?** Three people might write three matchers for housing, childcare, and employment. If each one calculates income tiers differently, three programs will disagree about what "第6档" means. So the translation from raw input to normalized buckets lives in one place, owned by one person.

---

### Stage 3: Write explanations (after we know the answer)

Now that we've decided yes or no, we ask AI to write a plain-language explanation.

```text
1. Take the decision we already made
   (program matches, amount, conditions)
   
2. Call Bailian AI
   → Pass program name, rule, and the decision
   → Ask: "Explain why they qualify in Chinese"
   
3. Get back plain text
   例: "您符合市场租房补贴条件，因为家庭人均月收入低于 4,200 元且无自有住房。—— 北京市住建委"
   
4. If Bailian is slow or fails:
   → Still show the amount and eligibility
   → Just skip the explanation paragraph
```

**Why fail-soft matters:** This is running live with real people. If Bailian times out (2 second timeout), we don't want the whole result to break. Show the amount and "yes/no," lose the explanation, move on. A missing explanation paragraph is fine. A broken amount is a disaster.

---

## What the rules look like

Here's a real example: the rental subsidy rule after Stage 1. This is what gets stored in `data/programs/bj_housing_market_rent_subsidy.json`.

```json
{
  "program_id": "bj_housing_market_rent_subsidy",
  "name": "市场租房补贴",
  "domain": "housing",
  "agency": "北京市住房和城乡建设委员会",
  "document_refs": ["京建法〔2015〕16号"],
  "source_url": "https://www.beijing.gov.cn/fuwu/bmfw/bmjy/...",

  "required_attributes": [
    "hukou_type", "household_size", "household_monthly_income",
    "household_assets", "owns_property", "district", "monthly_rent"
  ],

  "eligibility": { "all_of": [
    { "attr": "hukou_type", "op": "in", "value": ["bj_urban"] },
    { "attr": "per_capita_monthly_income", "op": "<=", "value": 4200 },
    { "attr": "owns_property", "op": "==", "value": false },
    { "attr": "household_assets", "op": "<=", "value": {
        "kind": "table", "keys": ["household_size_bucket"],
        "rows": [{ "household_size_bucket": "3+", "value": 570000 }] } }
  ]},

  "benefit": {
    "cadence": "monthly",
    "amount": {
      "kind": "table",
      "keys": ["income_tier", "household_size_bucket", "district_group"],
      "rows": [
        { "income_tier": 6, "household_size_bucket": "3+",
          "district_group": "standard", "value": 1200 }
      ]
    },
    "caps": [{ "kind": "not_to_exceed", "profile_field": "monthly_rent" }],
    "duration": { "kind": "ongoing_conditional", "review": "quarterly" }
  },

  "exclusivity_group": "bj_housing",
  "claim_steps": ["..."],
  "required_documents": ["..."],
  "confidence": "high",
  "notes": ""
}
```

**Five things this shape taught us:**

1. **Payments are three-dimensional:** income tier × household size × district. The rental subsidy alone has 24 different rates (not just one "you get ¥1,200").

2. **Thresholds are tables, not numbers:** The asset limit isn't a fixed amount. It's "¥57万 for small families, ¥76万 for large families."

3. **Same program, different buckets:** Household size matters twice in different ways. We use ≤2/3+ to decide the payment tier, but ≤3/≥4 to decide the asset limit. Both are in the same policy document.

4. **Tiers aren't always income brackets:** 第一档 and 第二档 aren't just "income ¥X to ¥Y". Some are official statuses (低保, 特困, officially designated low-income families). One household might be tier-2 because they have a specific government status, not because of their raw income.

5. **"Ongoing" means no end date:** The policy says "paid monthly, must stay qualified." This isn't "24 months then stops." It's "keeps going as long as they keep qualifying, reviewed quarterly." There's no lifetime total to calculate.

These quirks weren't obvious until we actually extracted the policy. This is why we don't freeze the schema until all six programs are done—they'll probably break more assumptions.

### Special cases: Can raise a payment but not lower it

Some rules in the policy say "you might get MORE if you qualify for this extra status." For example, if you're a special-needs household, the rental subsidy goes up by one tier.

We could ask five more intake questions to catch all of these. Instead, we note them as `benefit_caveats`: "Here's your base payment, but you might qualify for more—ask at the office."

This is safe in one direction only: you can *guess conservatively* (show the lower amount) and tell them they might get more. You absolutely cannot guess the opposite—if you show a higher payment but they don't actually qualify, that's worse than sending them to the wrong office. So:

- **Caveats (might get more):** Safe. Show base amount, mention possibility.
- **Requirements (might get less):** Unsafe. Must ask, not guess.

### Measuring confidence

`confidence` isn't a feeling. It's a fact about whether the three extraction passes agreed with each other.

| All 3 passes agree on every number and threshold | `high` |
| They disagree on something (amount, boundary, tier) | `medium` — note the disagreement |
| Passes can't find the info or give conflicting sources | `low` — needs human review |

We run the same extraction three times (might use different AI models). If they all say the same thing, that's strong evidence the rule is right. If they disagree, we record what they disagreed on and flag it for review.

It costs nothing to run three passes. We'd rather spend 3 seconds of compute than have a human hunt down a mistake later.

### What we need to know

The old form asked only five questions. That's not enough. Even just the rental subsidy alone needs seven questions (district, actual rent, household assets—none of which were asked before).

Here's what we need:

| Data | Why |
|------|-----|
| hukou_type | Beijing urban / rural / non-resident — affects eligibility |
| household_size | Number of people |
| household_monthly_income | Total household income |
| household_assets | Cash, savings, investments |
| owns_property | Do they own a home? |
| district | Which Beijing district? (affects payment tier) |
| monthly_rent | How much rent do they actually pay? (caps the payment) |
| employment_status | (needed for employment programs) |
| children_ages | (needed for childcare programs) |

**Smart questioning:** Don't ask everything up front. First, ask the gating questions (the small set that applies to all programs). Then show people which programs are still potentially eligible, and ask only the follow-up questions needed for those programs.

This way, someone might answer 3 initial questions, then 2 follow-ups—not 9 questions all at once. It feels less like a survey.

---

## How a request flows through the system

```
Person visits website
    ↓
Answer intake questions (e.g., income, family size)
    ↓
Send to backend /profile/confirm
    Backend checks: which programs might they qualify for?
    → if they're missing info, ask follow-up questions
    ↓ 
Person answers follow-ups (e.g., which district?)
    ↓
Send to backend /profile/finalize
    Backend does all matching:
    • Check each program's eligibility rules
    • Look up payment amount in tables
    • Apply caps (e.g., rent limit)
    • Sort by confidence and amount
    • Call Bailian for explanations (2s timeout, fail-soft)
    ↓
Backend returns: ranked list of programs with amounts and explanations
    ↓
Show results page
```

**Three API endpoints, no sessions.** The website is stateless. The person's household info travels back and forth in the request, not stored on the server. No login, no cookies, no persistence. After they close the tab, it's gone.

### Show monthly and one-time payments separately

Never add ¥1,200 per month to ¥5,000 one-time into one total. They're completely different:

- **¥1,200/month** = recurring, every month
- **¥5,000 one-time** = once, then done

Adding them together (¥6,200) makes no sense. Show them as two separate amounts.

(Right now all housing programs are monthly, so this isn't used yet. But we're building the page layout now so it doesn't surprise us later.)

### When two programs conflict

Some programs exclude each other: "you can get housing subsidy OR rental subsidy, but not both." When this happens:

1. **Show the bigger payment first**, but also show the other one as an alternative.
2. **Never silently hide the smaller option** — the person might prefer it for other reasons.
3. **Compare fairly** — don't compare ¥1,200/month to ¥5,000 one-time as if they're the same. Compare monthly to monthly, one-time to one-time.

### Ranking across all programs

1. **Confidence first** — a high-confidence ¥800 program shows before a low-confidence ¥1,200 program. We trust the high-confidence one more.
2. **Amount second** — if confidence is the same, higher payment comes first.

---

## What we're NOT building (and why)

These are tempting additions that would break the core design:

- **No document auto-scraping.** We could write a bot to find policies on government sites. Nope. Policy sourcing stays manual. We know what we got and why.

- **No LLM in the matching phase.** The core matching logic (Stage 2) is pure code, no AI. If we let AI decide eligibility, we lose reproducibility. Same person, same answer every time.

- **No vector database.** We use Bailian's managed knowledge base for extraction. We don't manage our own database of policies.

- **No login/accounts.** No session state, no memory of past conversations. Simpler, privacy-friendly, and one less thing to break.

- **No application submission.** We tell you what to claim, but we don't process the application. You go to the government office.

- **No AI agent framework.** Stage 3 parallelism is just `asyncio.gather()` over three function calls, not a full agent framework.

(Agents love adding databases and frameworks. This list is the answer when you're tempted.)

---

## Known issues and lessons learned

**Reproducibility works.** We ran extraction three times on the rental subsidy. All three passes agreed on every number and threshold. It's strong evidence the rules are right.

**AI makes confident mistakes.** When we asked AI "is this made-up household eligible?", it invented household details (hukou type, assets) to justify a yes, then declared them approved. Lesson: ask for rules, not eligibility. In an extraction, there's no household to invent.

**Missing exclusions are dangerous.** The retrieval system found the eligibility criteria but missed the "you can't claim this if you already got that" clauses. Because retrieval budgets chunks by relevance, and the good-eligibility text scores higher overall than obscure exclusions. Lesson: ask explicitly for disqualifying clauses.

**Output format matters for reproducibility.** Bailian's console app returns markdown prose, not the structured JSON the extraction prompt requested. So we can't automatically diff passes to detect disagreement—a human has to read them side-by-side. We'd fix this with a custom-configured extraction app, but haven't yet.

**Future:** Show source and verification date on every card (not yet designed). Maybe a visualization of "if all Beijing residents claimed these subsidies, total spend would be X"—illustrates scale and impact.
