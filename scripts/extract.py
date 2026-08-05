"""Stage 1: Bailian reads a policy document and drafts a structured rule.

    python scripts/extract.py bj_housing_market_rent_subsidy
    python scripts/extract.py bj_housing_market_rent_subsidy --passes 3
    python scripts/extract.py --all

Runs the versioned extraction prompt (docs/extraction-prompt.md) against the
Bailian app N times, writes every raw pass to data/extractions/, and diffs them
to suggest a confidence level.

Two things it deliberately does NOT do:

  - It never writes data/programs/*.json. A human reads the extraction and
    writes the rule file. That review is the gate, and automating it away would
    make `verified: true` meaningless.
  - It never records a 文号 or a source URL. Those come from data/manifest.json,
    written by whoever downloaded the PDF. A model-supplied citation is a
    fabrication risk with no upside, since we already know the answer.

Auth comes from the `bl` CLI, not from this repo. Run `bl auth login --api-key
<key>` once; nothing here reads or stores a credential. (backend/explain.py is
different -- it's in a request path and calls HTTP directly, because spawning a
subprocess per web request would be silly.)
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = ROOT / "data" / "manifest.json"
PROMPT_PATH = ROOT / "docs" / "extraction-prompt.md"
EXTRACTIONS_DIR = ROOT / "data" / "extractions"

DEFAULT_APP_ID = "8b47474cfc23490aa005109d875f3b0e"  # "Subsidy Q&A"


def _first_code_block(text: str) -> str:
    match = re.search(r"```(?:text)?\s*\n(.*?)```", text, re.DOTALL)
    return match.group(1).strip() if match else ""


def load_prompt() -> tuple[str, dict[str, str], int]:
    """Read the preamble and per-section queries from docs/extraction-prompt.md.

    One call per section, deliberately. Final recall is 5 chunks; a single call
    asking for eligibility, amounts, exclusions and procedure spends all five on
    whatever scores highest overall, which is the eligibility and amount text.
    That is how v1 returned a complete 24-cell benefit table and not one
    exclusion clause. Each section gets its own recall budget.
    """
    text = PROMPT_PATH.read_text(encoding="utf-8")

    version_match = re.search(r"\*\*Version:\s*(\d+)\*\*", text)
    version = int(version_match.group(1)) if version_match else 0

    _, _, preamble_part = text.partition("## Preamble")
    preamble = _first_code_block(preamble_part)
    if not preamble:
        raise ValueError("docs/extraction-prompt.md has no '## Preamble' code block")

    sections: dict[str, str] = {}
    for name, body in re.findall(r"## Section:\s*(\S+)\s*\n(.*?)(?=\n## |\Z)", text, re.DOTALL):
        query = _first_code_block(body)
        if query:
            sections[name] = query
    if not sections:
        raise ValueError("docs/extraction-prompt.md has no '## Section:' blocks")

    return preamble, sections, version


def load_manifest() -> dict[str, dict]:
    payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return {doc["program_id"]: doc for doc in payload.get("documents", [])}


def call_bailian(app_id: str, prompt: str, timeout: int = 180) -> str:
    """One `bl app call`. Auth is whatever the CLI is already configured with."""
    result = subprocess.run(
        ["bl", "app", "call", "--app-id", app_id, "--prompt", prompt],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        env={**__import__("os").environ, "NO_COLOR": "1"},
        shell=sys.platform == "win32",
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"bl app call failed (exit {result.returncode}):\n"
            f"{(result.stderr or result.stdout).strip()}"
        )
    return result.stdout.strip()


def parse_json_block(raw: str) -> dict | None:
    """Pull the JSON object out of the reply. Returns None if there isn't one."""
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    candidate = fenced.group(1) if fenced else None

    if candidate is None:
        start = raw.find("{")
        end = raw.rfind("}")
        candidate = raw[start : end + 1] if start != -1 and end > start else None

    if candidate is None:
        return None
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return None


def _comparable(parsed: dict) -> dict:
    """The parts of an extraction that passes must agree on to count as agreeing.

    Deliberately narrow: thresholds, amounts and exclusion counts. Wording drifts
    between passes and that drift is not disagreement -- two correct answers can
    be phrased differently, and treating that as a conflict would make every
    program low-confidence for no reason.
    """
    facts = {
        str(f.get("attr")): (f.get("operator"), json.dumps(f.get("threshold"), sort_keys=True, ensure_ascii=False))
        for f in parsed.get("required_facts") or []
    }
    table = parsed.get("benefit_table") or {}
    rows = sorted(
        json.dumps({"keys": r.get("keys"), "amount": r.get("amount")}, sort_keys=True, ensure_ascii=False)
        for r in table.get("rows") or []
    )
    return {
        "facts": facts,
        "cadence": table.get("cadence"),
        "rows": rows,
        "exclusion_count": len(parsed.get("exclusions") or []),
    }


def diff_passes(parsed: list[dict]) -> tuple[str, list[str]]:
    """Suggest a confidence level from how much the passes agree.

    Only a suggestion. A human still decides, because agreement between passes
    of the same model means less than it looks -- three passes tend to make the
    same mistake, so agreement can overstate confidence. Varying the model
    between passes would decorrelate that; varying only the prompt would not.
    """
    usable = [p for p in parsed if p]
    notes: list[str] = []

    if not usable:
        return "low", ["no pass returned parseable JSON"]
    if len(usable) < len(parsed):
        notes.append(f"{len(parsed) - len(usable)} of {len(parsed)} passes returned unparseable output")

    shapes = [_comparable(p) for p in usable]
    first = shapes[0]

    if all(s == first for s in shapes[1:]) and len(usable) > 1:
        confidence = "high"
    else:
        confidence = "medium"
        for key in ("cadence", "rows", "exclusion_count"):
            values = {json.dumps(s[key], sort_keys=True, ensure_ascii=False) for s in shapes}
            if len(values) > 1:
                notes.append(f"passes disagree on {key}: {sorted(values)}")
        all_attrs = {a for s in shapes for a in s["facts"]}
        for attr in sorted(all_attrs):
            variants = {json.dumps(s["facts"].get(attr), ensure_ascii=False) for s in shapes}
            if len(variants) > 1:
                notes.append(f"passes disagree on threshold for {attr}: {sorted(variants)}")

    if len(usable) == 1:
        confidence = "low"
        notes.append("only one usable pass -- nothing to cross-check against")

    # Gaps the model reported itself are worth surfacing to the reviewer.
    for gap in {g for p in usable for g in (p.get("gaps") or [])}:
        notes.append(f"reported gap: {gap}")
    if not any(p.get("exclusions") for p in usable):
        notes.append(
            "NO exclusions found. Verify by hand -- a rule missing its 不得 / 除外 / "
            "已享受 clauses is too generous, and too generous is the dangerous direction."
        )

    return confidence, notes


def extract(program_id: str, entry: dict, app_id: str, passes: int, only: str | None) -> int:
    preamble, sections, prompt_version = load_prompt()
    program_name = entry.get("name", program_id)
    preamble = preamble.replace("{program_name}", program_name)

    if only:
        if only not in sections:
            print(f"unknown section '{only}'. Known: {', '.join(sections)}")
            return 1
        sections = {only: sections[only]}

    out_dir = EXTRACTIONS_DIR / program_id
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    print(f"\n{program_id} ({program_name}) -- prompt v{prompt_version}, "
          f"{len(sections)} section(s) x {passes} pass(es)")

    for section, query in sections.items():
        print(f"  [{section}]")
        raws: list[str] = []
        for index in range(1, passes + 1):
            print(f"    pass {index}/{passes} ...", end=" ", flush=True)
            try:
                raw = call_bailian(app_id, f"{preamble}\n\n{query}")
            except Exception as exc:
                print("FAILED")
                print(f"      {exc}")
                return 1
            raws.append(raw)
            print(f"{len(raw)} chars")

            (out_dir / f"{stamp}-{section}-pass{index}.md").write_text(
                f"<!-- program: {program_id} | section: {section} | pass: {index} | "
                f"prompt v{prompt_version} | app: {app_id} | {stamp} -->\n\n{raw}\n",
                encoding="utf-8",
            )

        # The app returns prose, not the JSON the preamble asks for -- its
        # console system prompt wins. So agreement can't be computed
        # structurally; flag the signals a reviewer should look at instead.
        for note in prose_signals(raws):
            print(f"      ! {note}")

    print(f"  written to data/extractions/{program_id}/")
    print(f"  NEXT: read the passes side by side. Where they disagree, open the PDF.")
    print(f"        Then write data/programs/{program_id}.json by hand.")
    return 0


def prose_signals(raws: list[str]) -> list[str]:
    """Cheap disagreement signals over prose passes.

    Not a substitute for reading them. The one finding that mattered most so far
    -- one pass quoting a 不得申请 clause that another pass said did not exist --
    is exactly the shape this catches: 未检索到 in some passes but not others.
    """
    notes: list[str] = []
    if len(raws) < 2:
        notes.append("only one pass -- nothing to cross-check against")
        return notes

    # Count, don't test presence. A pass that found five clauses and missed one
    # still contains 未检索到, so "any but not all" reads as agreement when the
    # passes actually disagree about almost everything.
    not_found = [r.count("未检索到") for r in raws]
    if max(not_found) - min(not_found) >= 2:
        notes.append(
            f"CONFLICT: 未检索到 counts differ across passes {not_found}. Some passes "
            "return quoted clauses where others say the source has none. Treat every "
            "quoted clause as unverified until the PDF is checked."
        )

    for keyword in ("不得", "已享受", "停止发放", "取消资格"):
        present = [keyword in r for r in raws]
        if any(present) and not all(present):
            notes.append(f"passes disagree on whether '{keyword}' appears in the source")

    lengths = [len(r) for r in raws]
    if max(lengths) > 2 * max(1, min(lengths)):
        notes.append(f"pass lengths vary widely {lengths} -- retrieval may be unstable")

    return notes


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("program_id", nargs="?", help="program to extract")
    parser.add_argument("--all", action="store_true", help="every program in the manifest")
    parser.add_argument("--passes", type=int, default=3, help="passes per section (default 3)")
    parser.add_argument("--section", help="run one section only, e.g. exclusions")
    parser.add_argument("--app-id", default=DEFAULT_APP_ID, help="Bailian app id")
    args = parser.parse_args()

    manifest = load_manifest()

    if args.all:
        targets = list(manifest.items())
    elif args.program_id:
        if args.program_id not in manifest:
            print(f"'{args.program_id}' is not in data/manifest.json. Known: "
                  f"{', '.join(manifest) or '(none)'}")
            return 1
        targets = [(args.program_id, manifest[args.program_id])]
    else:
        parser.print_help()
        return 1

    status = 0
    for program_id, entry in targets:
        if not entry.get("uploaded"):
            print(f"\n{program_id}: skipped -- not uploaded to the knowledge base yet "
                  f"(data/manifest.json says uploaded: false).")
            if not args.all:
                status = 1
            continue
        status |= extract(program_id, entry, args.app_id, args.passes, args.section)

    return status


if __name__ == "__main__":
    raise SystemExit(main())
