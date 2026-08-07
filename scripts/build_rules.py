"""Merge data/programs/*.json into data/rules.json, validating on the way.

Run this after every change to a program file. Never hand-edit rules.json; if
you get a merge conflict in it, delete it and rerun.

    python scripts/build_rules.py            # allows drafts, warns loudly
    python scripts/build_rules.py --strict   # refuses anything unverified

Strict mode is what should run before the demo. The default mode exists so that
work can continue while the policy data is still being extracted and checked.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.models import Rule  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PROGRAMS_DIR = ROOT / "data" / "programs"
MANIFEST_PATH = ROOT / "data" / "manifest.json"
OUTPUT_PATH = ROOT / "data" / "rules.json"


def _strip_comments(payload: dict) -> dict:
    """Drop _-prefixed keys. They're notes for humans, not schema."""
    return {k: v for k, v in payload.items() if not k.startswith("_")}


def load_programs() -> tuple[list[Rule], list[str]]:
    errors: list[str] = []
    rules: list[Rule] = []

    for path in sorted(PROGRAMS_DIR.glob("*.json")):
        try:
            raw = _strip_comments(json.loads(path.read_text(encoding="utf-8")))
            rule = Rule.model_validate(raw)
        except Exception as exc:
            errors.append(f"{path.name}: {exc}")
            continue

        if rule.program_id != path.stem:
            errors.append(
                f"{path.name}: program_id '{rule.program_id}' does not match filename"
            )
        rules.append(rule)

    return rules, errors


def load_manifest() -> dict[str, dict]:
    if not MANIFEST_PATH.exists():
        return {}
    payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return {doc["program_id"]: doc for doc in payload.get("documents", [])}


def validate(rules: list[Rule], manifest: dict[str, dict]) -> tuple[list[str], list[str]]:
    """Returns (errors, warnings). Errors are fatal in every mode."""
    errors: list[str] = []
    warnings: list[str] = []

    seen: set[str] = set()
    for rule in rules:
        if rule.program_id in seen:
            errors.append(f"duplicate program_id: {rule.program_id}")
        seen.add(rule.program_id)

    # Every amount must trace to a document. This check is only meaningful
    # because document_refs comes from the human-written manifest -- if the
    # same model wrote both the amount and the citation, it proves nothing.
    for rule in rules:
        entry = manifest.get(rule.program_id)
        if entry is None:
            warnings.append(f"{rule.program_id}: no entry in data/manifest.json")
        refs = rule.document_refs or (entry or {}).get("document_refs") or []
        if not refs:
            warnings.append(
                f"{rule.program_id}: no document_refs -- every amount must trace to a 文号"
            )

    # Exclusivity must be declared on both sides. A group of one usually means
    # somebody wrote the tag on one program and forgot the other.
    groups: dict[str, list[str]] = defaultdict(list)
    for rule in rules:
        if rule.exclusivity_group:
            groups[rule.exclusivity_group].append(rule.program_id)
    for group, members in groups.items():
        if len(members) < 2:
            warnings.append(
                f"exclusivity_group '{group}' has only {members} -- "
                "the other program is missing or hasn't declared it"
            )

    # A required attribute nothing evaluates, or a predicate reading an
    # attribute nobody declared, means the rule and the form disagree.
    for rule in rules:
        used = {p.attr for p in rule.eligibility.all_of if p.attr}
        for key_def in rule.key_definitions.values():
            used.add(key_def.attr)
        declared = set(rule.required_attributes)
        derived = {"per_capita_monthly_income", "per_capita_household_assets",
                   "num_children", "num_children_under_3",
                   "youngest_child_age", "oldest_child_age"}
        undeclared = used - declared - derived
        if undeclared:
            warnings.append(
                f"{rule.program_id}: reads {sorted(undeclared)} "
                "but doesn't list them in required_attributes"
            )

    for rule in rules:
        if not rule.verified:
            warnings.append(f"{rule.program_id}: verified=false (unreviewed extraction)")

    return errors, warnings


def main() -> int:
    # Windows consoles default to cp1252 and will crash on 文号. Every script
    # in this project prints Chinese, so this is not optional.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--strict",
        action="store_true",
        help="treat warnings as errors -- run this before the demo",
    )
    args = parser.parse_args()

    rules, load_errors = load_programs()
    manifest = load_manifest()
    errors, warnings = validate(rules, manifest)
    errors = load_errors + errors

    for warning in warnings:
        print(f"  WARN  {warning}")
    for error in errors:
        print(f"  ERROR {error}")

    if errors:
        print(f"\nBuild failed: {len(errors)} error(s).")
        return 1
    if args.strict and warnings:
        print(f"\nBuild failed under --strict: {len(warnings)} warning(s).")
        return 1

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(
            {
                "_generated": "by scripts/build_rules.py -- do not hand-edit",
                "programs": [r.model_dump(mode="json") for r in rules],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"\nWrote {OUTPUT_PATH.relative_to(ROOT)} -- {len(rules)} program(s), "
          f"{len(warnings)} warning(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
