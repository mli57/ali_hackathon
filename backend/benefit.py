"""How much money, once eligibility is settled.

Kept out of the matchers because it isn't a yes/no question and it turned out to
be the most complicated part of the first program we looked at. 市场租房补贴 is
a three-dimensional lookup (income tier x household-size bucket x district
group) with a cap applied afterwards -- there is no single number that is
correct for the program.
"""

from __future__ import annotations

from typing import Any

from backend.lookup import Resolution, lookup_table
from backend.models import Fixed, Rule, Table


def compute_amount(rule: Rule, attrs: dict[str, Any]) -> Resolution:
    """Base amount from the rule, then every cap applied in order."""
    spec = rule.benefit.amount

    if isinstance(spec, Fixed):
        base = Resolution(value=float(spec.value))
    elif isinstance(spec, Table):
        base = lookup_table(spec, rule.key_definitions, attrs)
    else:  # pragma: no cover - the discriminated union forbids this
        return Resolution(no_match=True)

    if not base.ok:
        return base

    amount = float(base.value)

    for cap in rule.benefit.caps:
        ceiling = attrs.get(cap.profile_field)
        if ceiling is None:
            # We know the entitlement but not whether it's capped. Ask, don't
            # assume -- assuming no cap overstates the payment.
            return Resolution(missing=[cap.profile_field])
        if cap.kind == "not_to_exceed":
            amount = min(amount, float(ceiling))

    return Resolution(value=round(amount, 2))
