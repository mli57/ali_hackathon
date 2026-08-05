# Subsidy Discovery Agent

**A tool to help people find Beijing government cash benefits they qualify for.**

Someone answers questions about their household. We tell them which programs they can apply to, how much money they'd get, and how to claim it.

**Current status:** Housing programs only. See `ITERATE.md` for what's next.

---

## Get started (3 commands)

```bash
# Step 1: Set up the rules
python scripts/build_rules.py

# Step 2: Start the backend (the thinking part)
python -m uvicorn backend.main:app --reload

# Step 3: Start the website (what people see)
python -m http.server 3000 --directory frontend
```

Open http://localhost:3000 and you're ready to try it.

**Always run tests before saving:** `python -m pytest tests/`

---

## How it works (three-step flow)

### Step 1: Turn policies into rules (before launch)
We read the government policy documents and turn them into a set of clear rules. An AI helps draft the rules, but a human always reviews and approves them before we use them. These rules live in `data/programs/`.

### Step 2: Match people to programs (when someone uses it)
When someone answers questions about their household, our code (not AI) checks them against these rules. No guessing, no network calls—just fast, reliable matching.

### Step 3: Explain the answer (after we decide)
Once we know they qualify, an AI writes a friendly explanation in plain language. But it can't change the answer—it just explains the yes or no that was already decided in Step 2.

---

## Extract rules from new policies

First, make sure you're logged in to the AI system (one time):
```bash
bl auth login --api-key <your-key>
```

Then extract rules from a policy document:
```bash
python scripts/extract.py bj_housing_market_rent_subsidy   # Draft rules from one program
python scripts/extract.py --all --passes 3                 # Draft all programs
```

This creates draft rule files in `data/extractions/`. A human then reviews these and creates the final rule files in `data/programs/`. The human review is what makes this trustworthy.

---

## Add explanations (optional)

The app works fine without AI explanations—people will just see amounts without the plain-language summary. To add them:

```bash
export BAILIAN_API_KEY=...
export BAILIAN_APP_ID=...
export BAILIAN_TIMEOUT=2.0     # optional: wait up to 2 seconds for explanation
```

---

## Important: This data is not verified yet

The numbers in `data/programs/bj_housing_market_rent_subsidy.json` came from AI reading the policy documents, but **nobody has checked them against the actual official policy PDFs yet**. Don't treat these as correct until someone has opened the original government documents and verified every number.

When you run `build_rules.py --strict` before the demo, it will refuse unverified programs.

**Results are for reference only, not official application decisions.**

---

## Learn more

- **Full architecture and design:** `CONTEXT.md`
- **Roadmap and next steps:** `ITERATE.md`
- **Folder structure:** `REPO_STRUCT.md`
