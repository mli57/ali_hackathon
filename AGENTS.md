# Subsidy Discovery Agent

**What this does:** Help Beijing residents find government cash benefits they qualify for. A person answers a few questions about their household, and we tell them which programs they can apply to, how much money they'd get, and how to claim it.

**Status:** We're focusing on housing subsidies first to prove the whole system works. We'll add childcare and employment programs after that.

---

## Quick start

```bash
# Prepare the rules (do this first)
python scripts/build_rules.py

# Start the backend API (handles the logic)
python -m uvicorn backend.main:app --reload

# Start the website (what people see)
python -m http.server 3000 --directory frontend
```

Then open http://localhost:3000.

**Test everything:** `python -m pytest tests/` (run before any changes)

---

## How it works (the one rule that matters)

**Numbers are calculated by code. Explanations are written by AI.**

Every ¥ amount, every yes/no decision—these are computed using hard rules, not guesses. An AI model only writes the plain-language explanation *after* we've already decided. This keeps results reliable and reproducible.

---

## Core principles (don't break these)

1. **Never hand-edit `data/rules.json`** — it's auto-generated. Edit the program files in `data/programs/` instead.

2. **Keep it simple** — no databases, no extra frameworks. If something seems to need one, stop and ask first.

3. **The AI can't change decisions** — extraction (pulling rules from PDFs) happens offline. Explanation (writing the plain-language summary) happens *after* we've already decided yes or no. This keeps results deterministic.

4. **Never invent sources** — citations (文号, links, agencies) come from `data/manifest.json`, written by humans. Never from AI. A fake source is the worst possible error.

5. **Unknown ≠ No** — if we can't verify something, mark it "needs verification" not "qualifies." Sending someone to a government office based on a guess is worse than saying "I don't know."

6. **Don't let the AI block results** — if the explanation request times out, show the amount and eligibility anyway, just without the explanation text.

7. **Keep monthly and one-time payments separate** — don't add ¥1,200/month to ¥5,000 one-time. They're different things.

8. **Stay in your lane** — don't edit code you don't own. See `docs/ownership.md` for who owns what.

9. **Run tests before finishing** — `python -m pytest tests/` catches mistakes early.

---

## Where to find things

- **How it all fits together:** `CONTEXT.md`
- **What's done and what's next:** `ITERATE.md`
- **Folder structure and why:** `REPO_STRUCT.md`
- **What we're NOT building:** `CONTEXT.md`, section "What we're not building"

---

## Current status

**Housing only.** The system runs end-to-end for rental subsidies, but the data hasn't been checked against the actual policies yet. Don't trust the numbers until someone has read the original documents and said "yes, this is correct."

See `ITERATE.md` for what still needs to happen.
