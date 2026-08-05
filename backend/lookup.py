"""Key resolution and table lookup, shared by predicate evaluation and benefit math.

Both the eligibility check and the amount calculation need to answer "which
income tier / district group / size bucket is this household in", so the logic
lives in one place rather than in both.

The important property here is that "I can't work this out" is a distinct
outcome from "no". Every function returns a Resolution carrying the attributes
it was missing, so the caller can route the program to needs_verification
instead of silently excluding it -- or worse, silently qualifying it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.models import KeyDefinition, Table

#: Row value meaning "matches any value of this key".
WILDCARD = "*"


@dataclass
class Resolution:
    value: Any = None
    missing: list[str] = field(default_factory=list)
    #: Set when every input was present but nothing matched -- an out-of-range
    #: income, a district the table doesn't cover. Distinct from `missing`,
    #: because the fix is a corrected rule rather than another question.
    no_match: bool = False

    @property
    def ok(self) -> bool:
        return not self.missing and not self.no_match


def resolve_key(name: str, key_def: KeyDefinition, attrs: dict[str, Any]) -> Resolution:
    """Compute one program-specific lookup key (income_tier, district_group, ...)."""
    # Categorical answers win over the range lookup. 低保/特困/低收入 status
    # sets the 档次 outright; income only decides it for everyone else.
    for override in key_def.overrides:
        actual = attrs.get(override.attr)
        if actual is None:
            return Resolution(missing=[override.attr])
        if actual == override.equals:
            return Resolution(value=override.value)

    raw = attrs.get(key_def.attr)
    if raw is None:
        return Resolution(missing=[key_def.attr])

    if key_def.kind == "range_lookup":
        for band in key_def.bands:
            if band.min is not None and raw < band.min:
                continue
            if band.max is not None and raw > band.max:
                continue
            return Resolution(value=band.value)
    elif key_def.kind == "set_lookup":
        for group_name, members in key_def.groups.items():
            if raw in members:
                return Resolution(value=group_name)

    if key_def.default is not None:
        return Resolution(value=key_def.default)
    return Resolution(no_match=True)


def resolve_keys(
    names: list[str],
    key_definitions: dict[str, KeyDefinition],
    attrs: dict[str, Any],
) -> tuple[dict[str, Any], list[str], list[str]]:
    """Resolve several keys. Returns (resolved, missing_attrs, unmatched_keys)."""
    resolved: dict[str, Any] = {}
    missing: list[str] = []
    unmatched: list[str] = []

    for name in names:
        # A key may just be a plain profile attribute with no definition.
        key_def = key_definitions.get(name)
        if key_def is None:
            if name in attrs:
                resolved[name] = attrs[name]
            else:
                missing.append(name)
            continue

        res = resolve_key(name, key_def, attrs)
        if res.missing:
            missing.extend(res.missing)
        elif res.no_match:
            unmatched.append(name)
        else:
            resolved[name] = res.value

    return resolved, missing, unmatched


def lookup_table(
    table: Table,
    key_definitions: dict[str, KeyDefinition],
    attrs: dict[str, Any],
) -> Resolution:
    """Find the row matching this household and return its `value`."""
    resolved, missing, unmatched = resolve_keys(table.keys, key_definitions, attrs)
    if missing:
        return Resolution(missing=sorted(set(missing)))
    if unmatched:
        return Resolution(no_match=True)

    for row in table.rows:
        if all(
            row.get(key) == WILDCARD or row.get(key) == resolved[key]
            for key in table.keys
        ):
            return Resolution(value=row.get("value"))

    # Every input known, no row covers it. Usually an incomplete rule -- the
    # extraction found some of the 档位 table but not all of it.
    return Resolution(no_match=True)
