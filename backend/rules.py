"""Load data/rules.json once at startup and hold it in memory.

Six programs. A database would be weight without benefit.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from backend.models import Rule

RULES_PATH = Path(__file__).resolve().parent.parent / "data" / "rules.json"


@lru_cache(maxsize=1)
def load_rules(path: Path | None = None) -> list[Rule]:
    target = path or RULES_PATH
    if not target.exists():
        raise FileNotFoundError(
            f"{target} not found. It is generated -- run `python scripts/build_rules.py`."
        )
    payload = json.loads(target.read_text(encoding="utf-8"))
    return [Rule.model_validate(entry) for entry in payload["programs"]]


def required_attributes(rules: list[Rule]) -> dict[str, list[str]]:
    """attribute -> the programs that need it. Drives the follow-up questions."""
    index: dict[str, list[str]] = {}
    for rule in rules:
        for attr in rule.required_attributes:
            index.setdefault(attr, []).append(rule.program_id)
    return index
