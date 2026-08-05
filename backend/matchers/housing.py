"""Housing domain matcher.

市场租房补贴 and 公共租赁住房货币补贴. They form the `bj_housing` exclusivity
group -- a household takes one or the other, never both. That conflict is
resolved by the aggregator, not here: this matcher's only job is to say what
each program independently returns for this household.

Deliberately thin. All the logic is in base.py so that the three domain matchers
can't drift apart, and so that adding the second housing program is a data
change rather than a code change.
"""

from __future__ import annotations

from typing import Any

from backend.matchers.base import match_domain
from backend.models import MatchResult, Rule

DOMAIN = "housing"


async def match(profile_attrs: dict[str, Any], rules: list[Rule]) -> list[MatchResult]:
    return await match_domain(DOMAIN, rules, profile_attrs)
