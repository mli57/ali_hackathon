"""Raw profile -> the attributes rules are actually written against.

The user knows their household income and how many people live with them. The
policy is written against 人均月收入. Something has to translate, and it lives
here so that three matcher authors don't each invent their own version.

Scope note: only *universal* derivations belong here. Income tiers, district
groups and household-size buckets are program-specific -- one program's 第6档
is not another's -- so those live in each rule's `key_definitions` and are
resolved by backend/lookup.py at match time.
"""

from __future__ import annotations

from typing import Any

from backend.models import Profile


def derive(profile: Profile) -> dict[str, Any]:
    """Return the flat attribute map that predicates and tables are evaluated against.

    Absent inputs produce absent outputs. Never guess a value -- a missing
    attribute becomes a follow-up question or a needs_verification result, and
    both of those are honest. A guessed one is not.
    """
    attrs: dict[str, Any] = profile.model_dump(exclude_none=True)

    size = profile.household_size
    income = profile.household_monthly_income
    if size and income is not None:
        attrs["per_capita_monthly_income"] = round(income / size, 2)

    if profile.household_assets is not None and size:
        attrs["per_capita_household_assets"] = round(profile.household_assets / size, 2)

    if profile.children_ages is not None:
        attrs["num_children"] = len(profile.children_ages)
        # 育儿补贴 pays per eligible child, so the count that decides the money
        # is not num_children -- a household of [1, 5] has two children and one
        # subsidy. youngest_child_age decides *whether* they qualify; this
        # decides *how many times*.
        attrs["num_children_under_3"] = sum(1 for age in profile.children_ages if age < 3)
        if profile.children_ages:
            attrs["youngest_child_age"] = min(profile.children_ages)
            attrs["oldest_child_age"] = max(profile.children_ages)

    return attrs


#: Attributes produced here rather than asked for. /profile/confirm must not
#: turn these into follow-up questions -- it should ask for their inputs instead.
DERIVED_ATTRIBUTES = frozenset(
    {
        "per_capita_monthly_income",
        "per_capita_household_assets",
        "num_children",
        "num_children_under_3",
        "youngest_child_age",
        "oldest_child_age",
    }
)

#: What to ask when a derived attribute is missing.
DERIVED_INPUTS: dict[str, tuple[str, ...]] = {
    "per_capita_monthly_income": ("household_monthly_income", "household_size"),
    "per_capita_household_assets": ("household_assets", "household_size"),
    "num_children": ("children_ages",),
    "num_children_under_3": ("children_ages",),
    "youngest_child_age": ("children_ages",),
    "oldest_child_age": ("children_ages",),
}


def inputs_for(attr: str) -> tuple[str, ...]:
    """Map a required attribute back to the question(s) that would supply it."""
    return DERIVED_INPUTS.get(attr, (attr,))
