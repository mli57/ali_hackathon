# Setup

From a fresh clone to a working demo. Should take about five minutes.

If you just want to know what the project *is*, read `README.md` first — this file
only covers getting it running.

---

## Requirements

- **Python 3.10 or newer.** The code uses `X | None` annotations that Pydantic
  evaluates at import time, so 3.9 will fail on the first model. Developed and tested
  on 3.14.
- **A terminal that can print Chinese.** Every script here prints 文号 and policy text.
  On Windows, `cmd.exe` defaults to cp1252 and will crash — the scripts call
  `reconfigure(encoding="utf-8")` to protect themselves, but if you pipe their output
  anywhere, set `PYTHONIOENCODING=utf-8`.
- Nothing else. No database, no Docker, no Node (unless you want to re-run extraction
  — see the optional section at the bottom).

---

## 1. Install

```bash
git clone <repo-url>
cd ali_hackathon

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

python -m pip install -r requirements.txt
```

`.venv/` is already in `.gitignore`.

## 2. Build the rules

```bash
python scripts/build_rules.py
```

This merges `data/programs/*.json` into `data/rules.json`, validating on the way.
Expect it to print warnings — see "What the warnings mean" below. It exits 0 anyway;
that is deliberate, so work can continue while the policy data is still being checked.

**Never hand-edit `data/rules.json`.** It is generated. Edit the program files in
`data/programs/` and re-run this.

## 3. Run the tests

```bash
python -m pytest tests/
```

**28 tests, all passing.** Run this before you change anything, so you know the
baseline was green when you started. It needs no network and no API key — the whole
deterministic path (derive → match → benefit → aggregate) runs offline by design.

## 4. Start it

Two processes, two terminals. Both need the venv active.

```bash
# Terminal 1 -- the API
python -m uvicorn backend.main:app --reload

# Terminal 2 -- the website
python -m http.server 3000 --directory frontend
```

Open <http://localhost:3000>.

Sanity check the API on its own:

```bash
curl http://127.0.0.1:8000/health
```

The frontend talks to `http://127.0.0.1:8000` by default. To point it elsewhere, set
`window.API_BASE` before `app.js` loads.

---

## What the warnings mean

`build_rules.py` will tell you:

```
WARN  bj_housing_market_rent_subsidy: no document_refs -- every amount must trace to a 文号
WARN  exclusivity_group 'bj_housing' has only [...] -- the other program is missing
```

Both are expected right now and neither blocks you:

- **no document_refs** — nobody has opened the source PDF and recorded its 文号 in
  `data/manifest.json` yet. That is a manual task, not a code one.
- **exclusivity_group has only one member** — the second housing program
  (`公共租赁住房货币补贴`) has not been uploaded to the knowledge base yet.

`python scripts/build_rules.py --strict` turns warnings into failures and currently
exits 1. That is the gate that should pass before a demo, not a sign you installed
something wrong.

### Heads-up on the data

The numbers in `data/programs/` came from an AI reading the policy documents. Nobody
has checked them against the original PDFs. Don't quote a figure from this system to a
real person yet.

The rule file currently carries `verified: true`, which suppresses the 数据未经复核
banner on the results cards — that flag is wrong and is finding #1 in
`recommendations.md`. If your cards look confidently sourced, that is the bug, not the
truth.

---

## Optional: Stage 3 explanations

The results cards show an AI-written paragraph explaining each verdict. This is
**decoration** — every ¥ figure and every yes/no is computed in Python before the model
is called, and `backend/explain.py` swallows every failure and returns `None`. With no
key configured, cards render with all their numbers and one paragraph missing.

To turn it on:

```bash
export BAILIAN_API_KEY=sk-...
export BAILIAN_APP_ID=<your Bailian application id>

# Optional overrides:
export BAILIAN_TIMEOUT=2.0       # seconds; the hard cap on the whole batch
export BAILIAN_ENDPOINT=...      # if your app is not on the default DashScope URL
```

On Windows PowerShell: `$env:BAILIAN_API_KEY = "sk-..."`.

Never commit these. `.env` is in `.gitignore`.

## Optional: re-running extraction

Only needed if you are adding a program or re-extracting an existing one. Everything
else in this file works without it.

`scripts/extract.py` shells out to the Bailian CLI, which is an npm package:

```bash
npm install -g bailian-cli      # provides the `bl` command
bl auth login --api-key sk-...  # stored by the CLI, not by this repo
bl --version                    # confirm it is on PATH
```

Then:

```bash
python scripts/extract.py bj_housing_market_rent_subsidy --passes 5
python scripts/extract.py bj_housing_market_rent_subsidy --section exclusions
```

This writes raw passes to `data/extractions/<program_id>/` and **never** writes
`data/programs/*.json`. A human reads the extraction and writes the rule file — that
review is the gate.

Budget the time: 5 passes × 4 sections is 20 calls at roughly 60–120 seconds each, so
about an hour. Before spending it, read `metrics_report.md` — the last full run
produced 13 unusable passes out of 20, and the cause is the app's configuration rather
than the prompt.

---

## Where to go next

| I want to… | Read |
|---|---|
| understand the architecture | `CONTEXT.md` |
| know what is done and what is next | `ITERATE.md` |
| find which folder owns what | `REPO_STRUCT.md` |
| know the rules I must not break | `AGENTS.md` |
| see what is currently wrong with the data | `recommendations.md` |
