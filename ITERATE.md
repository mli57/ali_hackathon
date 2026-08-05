# Roadmap

**Strategy: Build one complete domain first, then add the others.**

If we build all three housing + childcare + employment at the same time, half-finished code is confusing. Better to finish housing completely, prove the whole system works end-to-end, then repeat for the next domain.

**Current status (August 6, 2026):** Housing rental subsidy is fully built and working, but the numbers aren't verified yet. We need a human to check the data against the original government documents.

---

## v0.1.0 — Beijing Rental Subsidy (市场租房补贴) — WORKING BUT NOT VERIFIED

**What's done:** The whole system runs start to finish. Put in a household, get the payment amount, an explanation of why they qualify, and steps to claim it. Every time, same answer.

**Why it says "unverified":** The AI read the policy document and extracted the rules. Three separate AI reads agreed with each other, which is good. But nobody has opened the actual government PDF to check if the AI got it right. Until someone does that, we can't trust the numbers.

The checks we got:
- Three AI passes agreed on all amounts ✓
- The payment table is internally consistent (outer districts are 60% of central, every time) ✓
- **The actual policy document has not been read** ✗

So we keep `verified: false` in the code. The `/health` endpoint reports this as unverified. The website shows "数据未经复核" (data not verified). Only after a human checks the PDF do we set `verified: true`.

### What's left to finish housing rental subsidy

These are all manual (non-code) tasks:

| Task | Person | Time |
|------|--------|------|
| **1. Check the numbers** — Open the real government PDF. Look at the payment table (24 different rates), check that the ¥4,200 income limit is right, verify the asset limits (¥57万 for small families, ¥76万 for large) | Anyone with access to the PDF | ~20 min |
| **2. Get the official document number** — Find the 文号 (official regulation number) on the PDF and write it into `data/manifest.json` | Same person | ~5 min |
| **3. Find the exclusions** — Search the PDF for any families that are NOT eligible (look for words like 不得 or 已享受). Right now the AI found a conflicting answer, so we need to check. | Same person | ~5 min |
| **4. Mark as verified** — Set `verified: true` in the code and run `python scripts/build_rules.py --strict` | Someone with code access | 2 min |

Done.

### One unresolved question

The AI gave two different answers about who's NOT eligible for rental subsidy. One pass says "families who already get public housing can't apply for rental subsidy." The other says "no such restriction found." Both are reading the same document, but they disagree.

This is the kind of mistake AI makes—it sounds plausible, so it's hard to catch. We need a human to open the actual PDF and settle it.

**Impact:** This doesn't stop the demo for housing rental subsidy alone. But it blocks linking rental subsidy to the other housing program (public rental subsidy).

See the full evidence in `data/extractions/bj_housing_market_rent_subsidy/20260806-exclusions-CONFLICT.md`.

### All three stages are built

**Stage 1 (Extract rules from PDFs):**
- ✓ Extraction script works and runs 3 times per program for consistency checking
- ✓ AI extracts the full 24-cell payment table
- ✓ Special cases handled (民政 status overrides, different household-size buckets for different rules)
- ✓ Script stores raw results in `data/extractions/` for human review
- ✗ Exclusion clauses: one rule missing, need to check PDF
- ✗ Document number (文号): not filled in yet

**Stage 2 (Match people to programs):**
- ✓ All core matching code written
- ✓ Household income translated into income tiers and buckets
- ✓ Payment lookup works (handles 3-dimensional table: income tier × household size × district)
- ✓ Rent cap is applied correctly
- ✓ Follow-up questions generated when info is missing

**Stage 3 (Write explanations):**
- ✓ AI explanation script written
- ✓ Tested with a broken endpoint to verify fail-soft works (missing explanation doesn't block results)
- ✗ Not yet tested with real Bailian API key

**Frontend:**
- ✓ Three pages: intake form → confirmation screen → results page
- ✓ Results show amount, why they qualify, how to claim, and verification status

**Tests:**
- ✓ 11 frozen test profiles covering edge cases
- ✓ 14 automated tests confirming same answer every time
- ✓ Regression tests for two bugs caught earlier

### Test results (current behavior)

| Household | Amount | Notes |
|---|---|---|
| 3 people, no special status, Chaoyang district, ¥3,800/person | ¥1,200/month | Baseline |
| 3 people, low-income official status, Chaoyang | ¥3,000/month | Higher tier |
| 3 people, dibao status, Chaoyang | ¥3,500/month | Highest urban tier |
| 3 people, dibao, Huairou (outer district) | ¥2,100/month | 60% of Chaoyang rate |
| 4 people with ¥70万 in assets | Qualifies | Under the ¥76万 limit for larger families |
| Monthly rent ¥800 less than what we'd pay | ¥800 | Rent cap prevents overpaying |
| Missing民政 status | Needs verification | Not guessed at |
| No income, no household info | Qualifies for nothing | Correctly filtered |

**Housing rental subsidy is done when:** someone has checked all these numbers against the real government PDF, the official document number is recorded, and `python scripts/build_rules.py --strict` exits clean.

---

## v0.1.1 — Add second housing program (公共租赁住房货币补贴)

The policy document for this program hasn't been uploaded to Bailian yet. It's a data-only change—the code is ready, just needs the rules extracted and verified. This ties the two housing programs together and tests the conflict resolution (when someone qualifies for both, pick the higher payment).

---

## v0.2.0 — Add childcare programs

Two programs: parenting subsidy (育儿补贴) and maternity allowance (生育津贴).

No new code needed. Just extract rules and build a childcare matcher following the same pattern as housing. If something doesn't fit, it means the housing abstraction is wrong—better to find that now than after building all six.

---

## v0.3.0 — Add employment programs

Two programs: flexible employment social insurance (灵活就业社保补贴) and one-time startup grant (一次性创业补贴).

This is where we test non-monthly benefits (the startup grant is a one-time payment). We'll need to show monthly and one-time payments separately on the results page.

---

## v0.4.0 — Free-text intake (optional, if time)

Let people describe their situation in plain language instead of filling a form. AI drafts their household info, they review and correct it. Nice to have, doesn't block the demo, can be cut if we're running short.

---

## v1.0.0 — Ready to show

All six programs working, all three stages tested, demo practiced, numbers verified.

---

## Future (after demo)

- Show the actual document link and official number (文号) on every card, plus when the data was verified
- Build a chart: total unclaimed subsidies in Beijing if no one knew about them → total paid if everyone who qualifies claimed it
- Medical domain (医保局) was in the original plan but cut from scope
- Live demo: drop a fresh PDF into Bailian during the presentation and watch a rule object auto-generate
