"""Predicate evaluation. Shared by every domain matcher.

Three outcomes, and the distinction between them is the whole safety story:

  excluded            a condition was checked and failed
  needs_verification  a condition could not be checked, or the policy text was
                      too vague to encode
  qualified           every condition was checked and passed

Anything unknown lands in needs_verification. Never in qualified. Telling
someone they qualify when we couldn't check sends a real person to a government
office for nothing, and that is the failure this whole design is arranged to
avoid.
"""

from __future__ import annotations

from typing import Any

from backend.lookup import Resolution, lookup_table
from backend.models import (
    Eligibility,
    KeyDefinition,
    MatchResult,
    Predicate,
    Rule,
    Table,
)

_COMPARISONS = {
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
    "in": lambda a, b: a in b,
    "not_in": lambda a, b: a not in b,
}


def describe(predicate: Predicate) -> str:
    """Human-readable form, used in failed_conditions so the UI can say why."""
    if predicate.note:
        return predicate.note
    if predicate.op == "manual_review":
        return predicate.clause or "需人工核验"
    return f"{predicate.attr} {predicate.op} {predicate.value}"


def _threshold(
    predicate: Predicate,
    key_definitions: dict[str, KeyDefinition],
    attrs: dict[str, Any],
) -> Resolution:
    """Resolve the right-hand side, which may itself be a table.

    The asset limit on 市场租房补贴 varies by household size, so the cutoff is
    a lookup rather than a number.
    """
    value = predicate.value
    if isinstance(value, dict) and value.get("kind") == "table":
        return lookup_table(Table.model_validate(value), key_definitions, attrs)
    if isinstance(value, Table):
        return lookup_table(value, key_definitions, attrs)
    return Resolution(value=value)


def evaluate(
    eligibility: Eligibility,
    key_definitions: dict[str, KeyDefinition],
    attrs: dict[str, Any],
) -> tuple[str, list[str], list[str], list[str]]:
    """Returns (status, unresolved_attributes, failed_conditions, review_clauses)."""
    unresolved: list[str] = []
    failed: list[str] = []
    review: list[str] = []

    for predicate in eligibility.all_of:
        if predicate.op == "manual_review":
            review.append(predicate.clause or describe(predicate))
            continue

        if predicate.attr is None:
            review.append(describe(predicate))
            continue

        left = attrs.get(predicate.attr)
        if left is None:
            unresolved.append(predicate.attr)
            continue

        right = _threshold(predicate, key_definitions, attrs)
        if right.missing:
            unresolved.extend(right.missing)
            continue
        if right.no_match:
            review.append(describe(predicate))
            continue

        try:
            passed = _COMPARISONS[predicate.op](left, right.value)
        except TypeError:
            # Mismatched types mean the rule and the profile disagree about
            # what this attribute is. Don't guess which is right.
            review.append(describe(predicate))
            continue

        if not passed:
            failed.append(describe(predicate))

    # A definite failure beats an unknown: if a checked condition failed, the
    # household is out regardless of what else we couldn't check.
    if failed:
        status = "excluded"
    elif unresolved or review:
        status = "needs_verification"
    else:
        status = "qualified"

    return status, sorted(set(unresolved)), failed, review


def result_for(rule: Rule, attrs: dict[str, Any]) -> MatchResult:
    """Evaluate one rule against one household. Shared by all domain matchers."""
    from backend.benefit import compute_amount  # local: benefit imports lookup too

    status, unresolved, failed, review = evaluate(
        rule.eligibility, rule.key_definitions, attrs
    )

    amount: float | None = None
    if status != "excluded":
        amount_res = compute_amount(rule, attrs)
        if amount_res.ok:
            amount = amount_res.value
        elif status == "qualified":
            # Eligible, but we can't say how much. That is not a qualified
            # result -- a card with no number is a promise we can't keep.
            status = "needs_verification"
            unresolved = sorted(set(unresolved) | set(amount_res.missing))
            if amount_res.no_match:
                review = [*review, f"{rule.name}：补贴金额表未覆盖此情况"]

    return MatchResult(
        program_id=rule.program_id,
        name=rule.name,
        domain=rule.domain,
        agency=rule.agency,
        status=status,
        amount=amount,
        cadence=rule.benefit.cadence,
        duration=rule.benefit.duration,
        unresolved_attributes=unresolved,
        failed_conditions=failed,
        review_clauses=review,
        caveats=rule.benefit_caveats if status == "qualified" else [],
        confidence=rule.confidence,
        verified=rule.verified,
        source_url=rule.source_url,
        document_refs=rule.document_refs,
        claim_steps=rule.claim_steps,
        required_documents=rule.required_documents,
        exclusivity_group=rule.exclusivity_group,
    )


async def match_domain(domain: str, rules: list[Rule], attrs: dict[str, Any]) -> list[MatchResult]:
    """The shared body of every domain matcher."""
    return [result_for(rule, attrs) for rule in rules if rule.domain == domain]
